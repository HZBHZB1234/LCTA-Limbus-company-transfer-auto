#!/usr/bin/env python3
"""solve_versioned.py - 无参考标准文件的 31 节映射求解（锚点间隙拼装）。

模型（经 08-06 真值验证）：
- 31 个标准节在物理空间按规范序首尾相连；每节物理位置 = entry.logical + adj，
  |adj| ≤ MAX_ADJ；逻辑序 == 物理序。
- 7 个受保护节（extractor：entry+adj+seed）为锚点，物理位置已知；
  锚点间隙内的非保护节按规范序平铺，与锚点衔接（padding ≤ 8）。
- padding 总量由锚点端点决定；分布用内容签名（rec-12/4 列单调率、
  text 可打印率）择优（08-06 的 +4 异常可由强签名 + 端点唯一确定）。

求解：
1. 受保护节按 rec 映射候选槽位集合（唯一 rec 直接钉死）。
2. 按物理序枚举锚点槽位组合（规范序递增）。
3. 逐间隙求解：槽位 rec 匹配条目 + padding（|logical - phys| ≤ MAX_ADJ），
   完成排序 = (内容分, -Σpads, -Σ|adj|) 字典序最大；跨间隙回溯。
4. 零尺寸节 snap 到 ≥ logical 的最小链边界。
"""

from __future__ import annotations

import struct

from .layouts import decrypt_bytes, detect_layout
from .versions import version_table

MAX_ADJ = 0x8000
PAD_MAX = 8
SCORE_MONO_SIZE = 1 << 20      # 单调列评分的大小上限（避免大节读取开销）
SCORE_TEXT_SIZE = 4 << 20
SCORE_MONO_MIN = 0.95


class SolveError(RuntimeError):
    pass


def _direct_reads(header: bytes, profile: dict) -> list[dict]:
    out = []
    for sec in profile.get("sections", []):
        size_off, offset_off = sec["size_off"], sec.get("offset_off")
        if size_off is None or offset_off is None:
            raise SolveError("profile sections 缺少 size_off/offset_off")
        size = struct.unpack_from("<i", header, size_off)[0]
        logical = struct.unpack_from("<i", header, offset_off)[0]
        adj = int(sec.get("adj", 0))
        out.append({
            "size_off": size_off,
            "offset_off": offset_off,
            "logical": logical,
            "size": size,
            "adj": adj,
            "phys": logical + adj,
            "seed": sec.get("seed"),
            "entry_index": size_off // 12,
        })
    return out


def _rec_of(entry: dict) -> int | None:
    if entry["count"] > 0 and entry["size"] > 0 and entry["size"] % entry["count"] == 0:
        return entry["size"] // entry["count"]
    return None


class _Scorer:
    """内容签名评分器（按 (entry, phys) 记忆化）。"""

    def __init__(self, metadata: bytes, by_index: dict) -> None:
        self.metadata = metadata
        self.by_index = by_index
        self.cache: dict[tuple, float] = {}

    def strong(self, entry: dict) -> bool:
        """是否有强签名（决定是否参与评分）。"""
        sz = entry["size"]
        return 12 <= sz <= SCORE_MONO_SIZE and sz % 4 == 0

    def score(self, entry_index: int, phys: int) -> float:
        key = (entry_index, phys)
        if key not in self.cache:
            self.cache[key] = self._compute(entry_index, phys)
        return self.cache[key]

    def align_score(self, phys: int) -> float:
        """对齐/死空间签名：物理位置 4 对齐 + 节起始 4 字节非全零。

        单调列签名对 4 对齐偏移免疫（索引列在错位时仍单调），无法区分
        ±4 死空间；真值位置恒满足 phys%4==0 且起始字节非全零
        （08-06 的 +4 异常正是靠这两点唯一确定）。
        """
        s = 0.0
        if phys >= 0 and phys % 4 == 0:
            s += 0.3
        if 0 <= phys < len(self.metadata) - 4:
            if any(b != 0 for b in self.metadata[phys:phys + 4]):
                s += 0.1
        return s

    def _compute(self, entry_index: int, phys: int) -> float:
        entry = self.by_index[entry_index]
        size = entry["size"]
        if size <= 0 or phys < 0 or phys + size > len(self.metadata):
            return 0.0
        data = self.metadata[phys:phys + size]
        score = 0.0
        if size <= SCORE_TEXT_SIZE:
            printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (9, 10, 13)) / size
            if printable >= 0.6:
                score = max(score, 0.7)
        if self.strong(entry):
            vals = struct.unpack(f"<{size // 4}I", data)
            best = 0.0
            for col in range(3):
                colvals = vals[col::3]
                if len(colvals) < 2:
                    continue
                nd = sum(1 for i in range(len(colvals) - 1) if colvals[i] <= colvals[i + 1])
                best = max(best, nd / (len(colvals) - 1))
            if best >= SCORE_MONO_MIN:
                score = max(score, 0.8)
            elif best >= 0.9:
                score = max(score, 0.5)
        return score


def solve(metadata: bytes, profile: dict, version: int = 39) -> dict:
    vt = version_table(version)
    names = vt["names"]
    rec = vt["rec"]

    header_size = profile["header_size"]
    header_seed = int(profile["header_seed"], 16)
    table = bytes.fromhex(profile["table_hex"])
    if len(table) != 256:
        raise SolveError("table_hex 长度 != 256")
    header = decrypt_bytes(metadata[:header_size], header_seed, table)
    layout, entries, scores = detect_layout(header, len(metadata))
    by_index = {e["index"]: e for e in entries}
    scorer = _Scorer(metadata, by_index)

    protected = _direct_reads(header, profile)
    if len(protected) < 5:
        raise SolveError(f"受保护节数量异常：{len(protected)}")
    prot_entries = {p["entry_index"] for p in protected}

    pool = []
    zero_entries = []
    for e in entries:
        if e["size"] == 0 and e["count"] == 0:
            zero_entries.append(e)
            continue
        if e["offset"] < 0:
            continue
        if e["offset"] + e["size"] > len(metadata) + 4:
            continue          # 越界辅助表（幻影）
        if e["index"] in prot_entries:
            continue
        pool.append(e)
    pool_by_rec: dict[tuple, list[dict]] = {}
    for e in pool:
        pool_by_rec.setdefault(_rec_of(e), []).append(e)

    review: list[str] = []

    # ---- 1. 受保护节候选槽位 ----------------------------------------------
    prot_sorted = sorted(protected, key=lambda p: p["phys"])
    slot_sets = []
    for p in prot_sorted:
        er = _rec_of(by_index[p["entry_index"]])
        slots = [i for i, n in enumerate(names)
                 if (rec[n] == er if er is not None else rec[n] is None)]
        if not slots:
            raise SolveError(f"受保护节 entry{p['entry_index']} 无匹配槽位（rec={er}）")
        slot_sets.append(slots)

    # ---- 2. 锚点槽位枚举 ---------------------------------------------------
    def enumerate_assignments(idx: int, chosen: list[int]) -> list[list[int]]:
        if idx == len(slot_sets):
            return [list(chosen)]
        out = []
        for s in slot_sets[idx]:
            if s <= (chosen[-1] if chosen else -1):
                continue
            chosen.append(s)
            out.extend(enumerate_assignments(idx + 1, chosen))
            chosen.pop()
        return out

    def gaps_of(slot_assign: list[int]) -> list[tuple[int | None, int | None, list[int]]]:
        gaps = []
        prev_slot = -1
        prev_end = None
        for i, s in enumerate(slot_assign):
            gaps.append((prev_end, prot_sorted[i]["phys"], list(range(prev_slot + 1, s))))
            prev_slot = s
            prev_end = prot_sorted[i]["phys"] + prot_sorted[i]["size"]
        gaps.append((prev_end, None, list(range(prev_slot + 1, 31))))
        return gaps

    # ---- 3. 逐间隙求解 -----------------------------------------------------
    def solve_gap(prev_end: int | None, next_start: int | None,
                  slots: list[int], used: set[int]) -> tuple[list, float] | None:
        """返回 (placements, score)；placements: [(slot, entry_index, phys)]。

        两段式搜索（避免 padding 组合爆炸）：
        a) 先枚举槽位条目序列（rec 匹配 + 位置近似约束）；
        b) 序列完成时由端点计算精确 padding 总量 Σ ∈ [P-8, P]，
           再枚举 Σ 在 m 个槽位上的分布（每槽 ≤ 8，位置校验）。
        """
        non_zero = [s for s in slots if rec[names[s]] != 0]
        if not non_zero:
            return [], 0.0
        best: tuple[tuple, list] | None = None
        m = len(non_zero)

        pads_used: list[int] = []

        def placements_rank(placements: list) -> tuple:
            sc = sum(scorer.score(e, ph) for (_, e, ph) in placements)
            sc += sum(scorer.align_score(ph) for (_, e, ph) in placements)
            # 死空间签名：节间 gap 字节全零 = 真实 padding（+0.15）；
            # 非零 = 该节实际被前移、真实数据被跳过（-0.15）。
            prev = prev_end
            for (_, e, ph) in placements:
                gap = ph - prev
                if 0 < gap <= PAD_MAX and 0 <= prev < len(metadata) - gap:
                    chunk = metadata[prev:ph]
                    if all(b == 0 for b in chunk):
                        sc += 0.15
                    else:
                        sc -= 0.15
                prev = ph + by_index[e]["size"]
            sadj = sum(abs(ph - by_index[e]["offset"]) for (_, e, ph) in placements)
            return (sc, -sum(pads_used), -sadj)

        def enumerate_pads(i: int, cum_sizes: int, cum_pads: int, sigma: int,
                           placements: list) -> None:
            """把 sigma 个 pad 分布到各槽位（每槽 ≤ 8，位置校验）。"""
            nonlocal best
            if i == m:
                if cum_pads == sigma:
                    key = placements_rank(placements)
                    if best is None or key > best[0]:
                        best = (key, [(s, e, ph) for s, e, ph in placements])
                return
            slot, eidx = placements[i][0], placements[i][1]
            er = by_index[eidx]
            base = prev_end + cum_sizes + cum_pads
            for pad in range(0, min(PAD_MAX, sigma - cum_pads) + 1):
                ph = base + pad
                if abs(ph - er["offset"]) > MAX_ADJ:
                    continue
                placements[i][2] = ph
                pads_used.append(pad)
                enumerate_pads(i + 1, cum_sizes + er["size"], cum_pads + pad,
                               sigma, placements)
                pads_used.pop()

        def finish(chosen: list) -> None:
            nonlocal best
            if prev_end is None:
                # 链首间隙：相对定位（物理位置由首个锚点反推）
                placements = []
                run = 0
                for slot, eidx in chosen:
                    placements.append([slot, eidx, run])
                    run += by_index[eidx]["size"]
                key = placements_rank(placements)
                if best is None or key > best[0]:
                    best = (key, [(s, e, p) for s, e, p in placements])
                return
            if next_start is None:
                # 链尾间隙：默认 pad=0；放置于 prev_end 累计
                placements = []
                run = prev_end
                for slot, eidx in chosen:
                    er = by_index[eidx]
                    placements.append([slot, eidx, run])
                    run += er["size"]
                key = placements_rank(placements)
                if best is None or key > best[0]:
                    best = (key, [(s, e, p) for s, e, p in placements])
                return
            cum_sizes = sum(by_index[e]["size"] for _, e in chosen)
            P = next_start - prev_end - cum_sizes
            if P < 0 or P > PAD_MAX * m:
                return
            placements = [[slot, eidx, 0] for slot, eidx in chosen]
            for sigma in range(max(0, P - PAD_MAX), P + 1):
                enumerate_pads(0, 0, 0, sigma, placements)

        def dfs_entries(i: int, chosen: list, used_local: set[int]) -> None:
            if i == m:
                finish(chosen)
                return
            slot = non_zero[i]
            er_target = rec[names[slot]]
            cands = pool_by_rec.get(None if er_target is None else er_target, [])
            for e in cands:
                if e["index"] in used or e["index"] in used_local:
                    continue
                if prev_end is not None:
                    # 位置近似约束：|(prev_end + 前序尺寸) - logical| 粗筛
                    cum = sum(by_index[ci]["size"] for _, ci in chosen)
                    if abs((prev_end + cum) - by_index[e["index"]]["offset"]) \
                            > MAX_ADJ + PAD_MAX * m:
                        continue
                chosen.append((slot, e["index"]))
                used_local.add(e["index"])
                dfs_entries(i + 1, chosen, used_local)
                used_local.discard(e["index"])
                chosen.pop()

        dfs_entries(0, [], set())
        if best is None:
            return None
        return best[1], best[0][0]

    best_solution: dict | None = None
    best_score = -1.0
    best_slot_assign: list[int] = []
    for slot_assign in enumerate_assignments(0, []):
        used = set(prot_entries)
        cur_sol: dict = {"sections": {}, "protected": {}, "evidence": {}}
        ok = True
        total_score = 0.0
        for prev_end, next_start, slots in gaps_of(slot_assign):
            res = solve_gap(prev_end, next_start, slots, used)
            if res is None:
                ok = False
                break
            placements, score = res
            total_score += score
            for slot, eidx, ph in placements:
                entry = by_index[eidx]
                used.add(eidx)
                cur_sol["sections"][names[slot]] = {
                    "custom_entry_index": eidx,
                    "physical_offset_adjustment": ph - entry["offset"],
                }
                cur_sol["evidence"][names[slot]] = {"physical": ph}
        if not ok:
            continue
        for ai, s in enumerate(slot_assign):
            p = prot_sorted[ai]
            eidx = p["entry_index"]
            cur_sol["sections"][names[s]] = {
                "custom_entry_index": eidx,
                "physical_offset_adjustment": p["adj"],
            }
            cur_sol["protected"][names[s]] = {
                "entry_index": eidx,
                "adj": p["adj"],
                "seed": p["seed"],
            }
            cur_sol["evidence"][names[s]] = {"physical": p["phys"], "protected": True}
        if total_score > best_score:
            best_score = total_score
            best_solution = cur_sol
            best_slot_assign = list(slot_assign)

    if best_solution is None:
        raise SolveError("无可行锚点槽位组合")

    solution = best_solution
    solution["layout"] = layout
    solution["entries"] = entries
    solution["anchor_slots"] = best_slot_assign

    # ---- 链首间隙反推：锚点前各节真实物理位置 --------------------------------
    pre_slots = [s for s in range(best_slot_assign[0]) if rec[names[s]] != 0]
    if pre_slots:
        first_anchor = prot_sorted[0]
        total_size = sum(by_index[solution["sections"][names[s]]["custom_entry_index"]]["size"]
                         for s in pre_slots)
        candidates = []
        for start in range(max(header_size, first_anchor["phys"] - total_size - PAD_MAX * len(pre_slots)),
                           first_anchor["phys"] - total_size + 1):
            run = start
            ok = True
            for s in pre_slots:
                entry = by_index[solution["sections"][names[s]]["custom_entry_index"]]
                if abs(run - entry["offset"]) > MAX_ADJ:
                    ok = False
                    break
                run += entry["size"]
            if ok and 0 <= first_anchor["phys"] - run <= PAD_MAX:
                candidates.append(start)
        if not candidates:
            review.append("链首间隙反推失败：锚点前节位置无法匹配 logical")
        else:
            run = candidates[0]
            for s in pre_slots:
                sec = solution["sections"][names[s]]
                entry = by_index[sec["custom_entry_index"]]
                sec["physical_offset_adjustment"] = run - entry["offset"]
                solution["evidence"][names[s]]["physical"] = run
                run += entry["size"]

    # ---- 零尺寸节 snap ----------------------------------------------------
    zero_names = [n for n in names if rec[n] == 0]
    used_e = {s["custom_entry_index"] for s in solution["sections"].values()}
    zero_cands = [e for e in zero_entries if e["index"] not in used_e]
    ev_starts = {v["physical"] for v in solution["evidence"].values()
                 if "physical" in v}
    ev_ends = {v["physical"] + by_index[solution["sections"][name]["custom_entry_index"]]["size"]
               for name, v in solution["evidence"].items() if "physical" in v}
    boundaries = sorted(ev_starts | ev_ends)
    for idx, entry in enumerate(zero_cands):
        if idx >= len(zero_names):
            review.append(f"零尺寸条目超出零尺寸名：entry{entry['index']}")
            break
        name = zero_names[idx]
        physical = next((b for b in boundaries if b >= entry["offset"]), None)
        if physical is None:
            review.append(f"entry{entry['index']} 无 ≥ logical 的边界")
            continue
        adj = physical - entry["offset"]
        if abs(adj) >= MAX_ADJ:
            review.append(f"entry{entry['index']} adj={adj} 超 C4 界")
            continue
        solution["sections"][name] = {
            "custom_entry_index": entry["index"],
            "physical_offset_adjustment": adj,
        }
        solution["evidence"][name] = {"physical": physical, "zero_size": True}

    missing = [n for n in names if n not in solution["sections"]]
    if missing:
        review.append(f"缺失节：{missing}")

    solution["review"] = review
    return solution
