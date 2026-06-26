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


def _load_json(filepath: Path) -> dict | None:
    """加载 JSON 文件，任何错误返回 None。"""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None
