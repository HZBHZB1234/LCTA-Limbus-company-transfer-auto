#!/usr/bin/env python3
"""report.py - 共享报告框架。

所有恢复组件统一通过本模块产出：
- report.json：机器可读（门、证据、复核项、裁决）
- report.md ：人类/LLM 可读的 Markdown 报告

裁决规则：
- FAIL            存在任何失败的 gate
- PASS_WITH_REVIEW 所有 gate 通过，但存在 requires_review 复核项
- PASS            所有 gate 通过且无复核项
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


VERDICT_FAIL = "FAIL"
VERDICT_PASS_WITH_REVIEW = "PASS_WITH_REVIEW"
VERDICT_PASS = "PASS"


@dataclass
class Gate:
    """一道验证门：通过/失败 + 证据。"""

    name: str
    passed: bool
    evidence: str = ""
    detail: list[str] = field(default_factory=list)


@dataclass
class ReviewItem:
    """需要人工/LLM 复核的歧义项。

    LLM 可离线凭 evidence 审核并给出结论，不阻塞流水线其余部分。
    """

    id: str
    question: str
    evidence: str = ""
    suggestion: str = ""
    status: str = "open"  # open | accepted | rejected


class Report:
    """聚合 gate 与复核项的报告对象。"""

    def __init__(self, tool: str, version: str = "", title: str = ""):
        self.tool = tool
        self.version = version
        self.title = title or f"{tool} 报告"
        self.gates: list[Gate] = []
        self.review_items: list[ReviewItem] = []
        self.sections: dict[str, Any] = {}
        self._next_review_id = 1

    # -- gates -----------------------------------------------------------

    def gate(self, name: str, passed: bool, evidence: str = "", **detail: Any) -> Gate:
        g = Gate(name=name, passed=bool(passed), evidence=evidence)
        for key, value in detail.items():
            if isinstance(value, list):
                g.detail.extend(str(v) for v in value)
            else:
                g.detail.append(f"{key}: {value}")
        self.gates.append(g)
        return g

    # -- review items ----------------------------------------------------

    def review(self, question: str, evidence: str = "", suggestion: str = "") -> ReviewItem:
        item = ReviewItem(
            id=f"R{self._next_review_id:03d}",
            question=question,
            evidence=evidence,
            suggestion=suggestion,
        )
        self._next_review_id += 1
        self.review_items.append(item)
        return item

    # -- extra data ------------------------------------------------------

    def set_section(self, name: str, data: Any) -> None:
        self.sections[name] = data

    # -- verdict ----------------------------------------------------------

    def verdict(self) -> str:
        if any(not g.passed for g in self.gates):
            return VERDICT_FAIL
        if self.review_items:
            return VERDICT_PASS_WITH_REVIEW
        return VERDICT_PASS

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "version": self.version,
            "title": self.title,
            "verdict": self.verdict(),
            "gates": [
                {
                    "name": g.name,
                    "passed": g.passed,
                    "evidence": g.evidence,
                    "detail": g.detail,
                }
                for g in self.gates
            ],
            "review_items": [
                {
                    "id": r.id,
                    "question": r.question,
                    "evidence": r.evidence,
                    "suggestion": r.suggestion,
                    "status": r.status,
                }
                for r in self.review_items
            ],
            "sections": self.sections,
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def write_md(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append(f"# {self.title}")
        if self.version:
            lines.append(f"\n版本/样本：`{self.version}`")
        lines.append(f"\n## 裁决：**{self.verdict()}**\n")
        lines.append("\n## 验证门\n")
        for g in self.gates:
            mark = "PASS" if g.passed else "**FAIL**"
            lines.append(f"- [{mark}] **{g.name}**  {g.evidence}")
            for d in g.detail:
                lines.append(f"  - {d}")
        if self.review_items:
            lines.append("\n## 需复核项\n")
            for r in self.review_items:
                lines.append(f"- **{r.id}** [{r.status}] {r.question}")
                if r.evidence:
                    lines.append(f"  - 证据：{r.evidence}")
                if r.suggestion:
                    lines.append(f"  - 建议：{r.suggestion}")
        else:
            lines.append("\n## 需复核项\n\n无。")
        for name, data in self.sections.items():
            lines.append(f"\n## {name}\n")
            lines.append(_render_data(data))
        path.write_text("\n".join(lines), encoding="utf-8")

    def write_all(self, base_dir: Path, name: str) -> tuple[Path, Path]:
        base_dir.mkdir(parents=True, exist_ok=True)
        json_path = base_dir / f"{name}.json"
        md_path = base_dir / f"{name}.md"
        self.write_json(json_path)
        self.write_md(md_path)
        return json_path, md_path


def _render_data(data: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}- {key}:")
                lines.append(_render_data(value, indent + 1))
            else:
                lines.append(f"{pad}- {key}: {value}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for value in data:
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}- {_render_data(value, indent + 1).strip()}")
            else:
                lines.append(f"{pad}- {value}")
        return "\n".join(lines)
    return f"{pad}{data}"


def load_report_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def report_from_dict(data: dict[str, Any]) -> Report:
    rep = Report(tool=data.get("tool", ""), version=data.get("version", ""), title=data.get("title", ""))
    for g in data.get("gates", []):
        rep.gate(g["name"], g["passed"], g.get("evidence", ""))
    for r in data.get("review_items", []):
        rep.review(r["question"], r.get("evidence", ""), r.get("suggestion", ""))
    rep.sections = data.get("sections", {})
    return rep


def main() -> int:
    parser = argparse.ArgumentParser(description="报告框架自测/工具")
    parser.add_argument("--selfcheck", action="store_true", help="运行内置自测")
    args = parser.parse_args()
    if args.selfcheck:
        rep = Report(tool="selfcheck", version="test")
        rep.gate("g1", True, "通过")
        rep.gate("g2", False, "失败")
        rep.review("这是歧义？", "证据 A", "建议 B")
        rep.set_section("notes", {"a": 1, "b": [1, 2]})
        rep.write_all(Path("out/selfcheck"), "report")
        assert rep.verdict() == VERDICT_FAIL
        rep2 = Report(tool="selfcheck", version="test")
        rep2.gate("g1", True, "ok")
        assert rep2.verdict() == VERDICT_PASS
        rep3 = Report(tool="selfcheck", version="test")
        rep3.gate("g1", True, "ok")
        rep3.review("q", "e")
        assert rep3.verdict() == VERDICT_PASS_WITH_REVIEW
        print("selfcheck OK")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
