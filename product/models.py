from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Issue:
    id: str
    severity: str
    title: str
    summary: str
    action_id: Optional[str] = None


@dataclass
class ActionDescriptor:
    id: str
    title: str
    summary: str
    intent: str
    availability: str = "available"
    blockers: List[str] = field(default_factory=list)
    recommended: bool = False


@dataclass
class ActionPlan:
    id: str
    action_id: str
    title: str
    inputs: Dict[str, Any]
    steps: List[Dict[str, Any]]
    changes: List[str]
    warnings: List[str]
    requirements: List[str]
    can_execute: bool
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OperationResult:
    success: bool
    summary: str
    changed_items: List[str] = field(default_factory=list)
    failed_items: List[str] = field(default_factory=list)
    next_actions: List[Dict[str, Any]] = field(default_factory=list)
    recovery: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
