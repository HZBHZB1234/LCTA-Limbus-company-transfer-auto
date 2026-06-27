"""
translateFunc/proper/analyze.py
JP/EN 上下文提取：对每个专有名词 KR 术语，在游戏文件中搜索包含它的句子，
并在相同结构位置提取对应的 JP/EN 句子。
"""
from __future__ import annotations
from pathlib import Path
import json

from translateFunc.proper.flat import flatten_dict_enhanced


def extract_contexts(
    kr_term: str,
    kr_path: Path,
    jp_path: Path,
    en_path: Path,
    max_examples: int = 20,
) -> list[dict]:
    """
    对给定的 KR 术语，搜索全部游戏 JSON 文件，提取包含该术语的句子
    （或文本值），并配对相同路径下的 JP/EN 文本。

    返回 [{kr_sentence, jp_sentence, en_sentence, file, path}, ...] 列表。
    """
    results: list[dict] = []
    kr_files = list(kr_path.rglob("*.json"))

    for kr_file in kr_files:
        if len(results) >= max_examples:
            break
        try:
            rel = kr_file.relative_to(kr_path)
            jp_file = jp_path / rel
            en_file = en_path / rel

            kr_data = _load_json(kr_file)
            if kr_data is None:
                continue
            jp_data = _load_json(jp_file) if jp_file.exists() else None
            en_data = _load_json(en_file) if en_file.exists() else None

            kr_flat = flatten_dict_enhanced(kr_data, ignore_types=[None, int, float])
            jp_flat = flatten_dict_enhanced(jp_data, ignore_types=[None, int, float]) if jp_data else {}
            en_flat = flatten_dict_enhanced(en_data, ignore_types=[None, int, float]) if en_data else {}

            for path_tuple, kr_text in kr_flat.items():
                if len(results) >= max_examples:
                    break
                if not isinstance(kr_text, str):
                    continue
                if kr_term in kr_text and len(kr_text) > len(kr_term):
                    results.append({
                        "kr_sentence": kr_text,
                        "jp_sentence": jp_flat.get(path_tuple, ""),
                        "en_sentence": en_flat.get(path_tuple, ""),
                        "file": str(rel),
                        "path": path_tuple,
                    })
        except Exception:
            continue

    return results


def extract_contexts_batch(
    terms: list[str],
    kr_path: Path,
    jp_path: Path,
    en_path: Path,
    max_examples: int = 20,
) -> dict[str, list[dict]]:
    """
    批量提取多个术语的 JP/EN 上下文。单次文件扫描 + AC 自动机匹配。

    复杂度 O(文件数 x 键值对数 + 命中数)，对比逐术语调用的
    O(术语数 x 文件数 x 键值对数)，在 800+ 术语时约快 800 倍。

    Args:
        terms: 要搜索的 KR 术语文本列表
        kr_path: KR 游戏文件目录
        jp_path: JP 游戏文件目录
        en_path: EN 游戏文件目录
        max_examples: 每个术语最多收集的上下文条数

    Returns:
        {term: [{kr_sentence, jp_sentence, en_sentence, file, path}, ...], ...}
    """
    import logging
    from translateFunc.matcher.ac_automaton import AcAutomaton

    if not terms:
        return {}

    # 0. 去重，避免同一术语多次 add_pattern 导致重复匹配
    terms = list(dict.fromkeys(terms))

    # 1. 构建包含所有术语的 AC 自动机
    ac = AcAutomaton()
    for term in terms:
        if term:  # 跳过空术语
            ac.add_pattern(term)
    ac.build()

    # 2. 初始化结果容器
    results: dict[str, list[dict]] = {term: [] for term in terms if term}
    # term_counts 跟踪每个术语已找到的上下文数
    term_counts: dict[str, int] = {term: 0 for term in terms if term}

    kr_files = list(kr_path.rglob("*.json"))
    logging.info(f"开始专有名词上下文分析，共 {len(terms)} 个术语，{len(kr_files)} 个文件")

    total_hits = 0

    # 3. 单次扫描所有文件
    for kr_file in kr_files:
        # 检查是否所有术语都已达到上限
        if all(count >= max_examples for count in term_counts.values()):
            break

        try:
            rel = kr_file.relative_to(kr_path)
            jp_file = jp_path / rel
            en_file = en_path / rel

            kr_data = _load_json(kr_file)
            if kr_data is None:
                continue
            jp_data = _load_json(jp_file) if jp_file.exists() else None
            en_data = _load_json(en_file) if en_file.exists() else None

            kr_flat = flatten_dict_enhanced(kr_data, ignore_types=[None, int, float])
            jp_flat = flatten_dict_enhanced(jp_data, ignore_types=[None, int, float]) if jp_data else {}
            en_flat = flatten_dict_enhanced(en_data, ignore_types=[None, int, float]) if en_data else {}

            for path_tuple, kr_text in kr_flat.items():
                if not isinstance(kr_text, str):
                    continue

                # 用 AC 自动机搜索当前文本值
                hits = ac.search(kr_text)
                for hit in hits:
                    term = hit.pattern
                    # 过滤：文本值恰好等于术语时不应收录（无上下文意义）
                    if len(kr_text) <= len(term):
                        continue
                    if term_counts.get(term, 0) >= max_examples:
                        continue

                    results[term].append({
                        "kr_sentence": kr_text,
                        "jp_sentence": jp_flat.get(path_tuple, ""),
                        "en_sentence": en_flat.get(path_tuple, ""),
                        "file": str(rel),
                        "path": path_tuple,
                    })
                    term_counts[term] = term_counts.get(term, 0) + 1
                    total_hits += 1

        except Exception:
            continue

    matched_terms = sum(1 for v in results.values() if v)
    logging.info(
        f"专有名词上下文分析完成，命中 {total_hits} 处，"
        f"覆盖 {matched_terms}/{len(terms)} 个术语"
    )
    return results


def _load_json(filepath: Path) -> dict | None:
    """加载 JSON 文件，任何错误返回 None。"""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None
