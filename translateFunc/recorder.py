"""
translateFunc/recorder.py
TranslationRecorder —— 单次翻译运行写入一个 JSONL 文件，线程安全追加。
"""
from __future__ import annotations
import json
import threading
from pathlib import Path


class TranslationRecorder:
    """单次翻译运行写入一个 JSONL 文件，每行一条文件翻译记录。"""

    def __init__(self, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path = file_path
        self._lock = threading.Lock()

    def write_record(self, record: dict) -> None:
        """追加一条翻译记录到 JSONL 文件。线程安全。"""
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(line)
