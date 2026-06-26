"""
translateFunc/matcher/ac_automaton.py
纯 Aho-Corasick 自动机实现。
不依赖游戏数据 —— 仅算法。

复杂度：
  构建: O(L)，L = 所有模式串长度之和
  搜索: O(m + k)，m = 文本长度，k = 命中数
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Any


@dataclass
class ACPattern:
    """自动机匹配到的单个模式。"""
    pattern: str
    node_id: int
    data: Any = None


class AcAutomaton:
    """Aho-Corasick 多模式字符串匹配自动机。"""

    def __init__(self):
        self._trie: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._output: list[list[ACPattern]] = [[]]
        self._built: bool = False

    def add_pattern(self, pattern: str, data: Any = None) -> None:
        """向自动机添加模式串。必须在调用 build() 之前完成。"""
        if self._built:
            raise RuntimeError("不能在 build() 之后添加模式")
        if not pattern:
            return
        node = 0
        for ch in pattern:
            if ch not in self._trie[node]:
                self._trie[node][ch] = len(self._trie)
                self._trie.append({})
                self._fail.append(0)
                self._output.append([])
            node = self._trie[node][ch]
        self._output[node].append(ACPattern(pattern=pattern, node_id=node, data=data))

    def build(self) -> None:
        """构建失败链接（BFS）。必须在所有 add_pattern() 调用之后执行。"""
        if self._built:
            return
        queue: deque[int] = deque()
        # 初始化深度为 1 的节点的失败链接
        for ch, child in self._trie[0].items():
            self._fail[child] = 0
            queue.append(child)
        # 广度优先构建
        while queue:
            r = queue.popleft()
            for ch, child in self._trie[r].items():
                queue.append(child)
                f = self._fail[r]
                while f != 0 and ch not in self._trie[f]:
                    f = self._fail[f]
                self._fail[child] = self._trie[f].get(ch, 0)
                self._output[child].extend(self._output[self._fail[child]])
        self._built = True

    def search(self, text: str) -> list[ACPattern]:
        """在文本中搜索所有模式。返回匹配的 ACPattern 列表。"""
        if not self._built:
            raise RuntimeError("必须在 search() 之前调用 build()")
        if not text:
            return []
        result: list[ACPattern] = []
        node = 0
        for ch in text:
            while node != 0 and ch not in self._trie[node]:
                node = self._fail[node]
            node = self._trie[node].get(ch, 0)
            if self._output[node]:
                result.extend(self._output[node])
        return result

    def search_batch(self, texts: list[str]) -> list[list[ACPattern]]:
        """批量搜索多个文本。每个输入文本返回一个匹配列表。"""
        return [self.search(t) for t in texts]

    @property
    def pattern_count(self) -> int:
        """已添加的模式总数。"""
        return sum(len(out) for out in self._output)

    @property
    def is_built(self) -> bool:
        return self._built
