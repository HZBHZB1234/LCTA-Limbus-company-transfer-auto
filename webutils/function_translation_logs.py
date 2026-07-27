"""Read, filter and export current translation diagnostic dumps."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO


CURRENT_SCHEMA_VERSION = 2
SUCCESS_CALL_STATUSES = {"success", "recovered"}
DEFAULT_PAGE_SIZE = 50
ALLOWED_PAGE_SIZES = {25, 50, 100}


@dataclass
class _CachedIndex:
    signature: tuple[int, int]
    entries: list[dict[str, Any]]
    facets: dict[str, list[str]]
    valid_count: int
    invalid_count: int
    unsupported_count: int


class TranslationLogService:
    """Read a user-selected current-version diagnostic JSONL file."""

    def __init__(self, log_dir: Path | str | None = None):
        self.log_dir = Path(log_dir or Path.cwd() / "logs" / "translation_dump").resolve()
        self._cache: dict[str, _CachedIndex] = {}
        self._lock = threading.RLock()

    def get_file_info(self, file_id: str, force_refresh: bool = False) -> dict[str, Any]:
        path = self._resolve_file(file_id)
        index = self._get_index(file_id, force_refresh=force_refresh)
        stat = path.stat()
        if index.valid_count == 0:
            raise ValueError("所选文件不包含当前 schema_version 2 的诊断记录")
        return {
            "id": path.name,
            "name": path.name,
            "path": str(path),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "record_count": len(index.entries),
            "valid_count": index.valid_count,
            "invalid_count": index.invalid_count,
        }

    def query_records(
        self,
        file_id: str,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        index = self._get_index(file_id, force_refresh=force_refresh)
        normalized_filters = self._normalize_filters(filters or {})
        page = max(1, int(page or 1))
        page_size = int(page_size or DEFAULT_PAGE_SIZE)
        if page_size not in ALLOWED_PAGE_SIZES:
            page_size = DEFAULT_PAGE_SIZE

        matched = [entry for entry in index.entries if self._matches(entry, normalized_filters)]

        total = len(matched)
        start = (page - 1) * page_size
        records = [self._public_summary(entry) for entry in matched[start:start + page_size]]
        return {
            "records": records,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "facets": index.facets,
            "invalid_count": index.invalid_count,
        }

    def get_record(self, file_id: str, line_number: int) -> dict[str, Any]:
        path = self._resolve_file(file_id)
        index = self._get_index(file_id)
        line_number = int(line_number)
        entry = next(
            (candidate for candidate in index.entries if candidate["line_number"] == line_number),
            None,
        )
        if entry is None:
            raise ValueError("指定的日志记录不存在")

        raw = self._read_entry(path, entry)
        if entry["invalid"]:
            return {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "line_number": line_number,
                "invalid": True,
                "parse_error": entry["parse_error"],
                "raw_line": raw.decode("utf-8", errors="replace").rstrip("\r\n"),
            }

        record = json.loads(raw)
        record["line_number"] = line_number
        record["invalid"] = False
        return record

    def export_filtered(
        self,
        file_id: str,
        filters: dict[str, Any] | None,
        destination: Path | str,
    ) -> dict[str, Any]:
        source = self._resolve_file(file_id)
        index = self._get_index(file_id)
        normalized_filters = self._normalize_filters(filters or {})
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        exported = 0
        skipped_invalid = 0
        with source.open("rb") as source_handle, destination_path.open("wb") as output:
            for entry in index.entries:
                if not self._matches(entry, normalized_filters):
                    continue
                if entry["invalid"]:
                    skipped_invalid += 1
                    continue
                raw = self._read_entry_from_handle(source_handle, entry).rstrip(b"\r\n")
                output.write(raw + b"\n")
                exported += 1

        return {
            "path": str(destination_path),
            "exported": exported,
            "skipped_invalid": skipped_invalid,
        }

    def _resolve_file(self, file_id: str) -> Path:
        if not isinstance(file_id, str) or not file_id or Path(file_id).name != file_id:
            raise ValueError("无效的日志文件标识")
        if Path(file_id).suffix.lower() != ".jsonl":
            raise ValueError("仅支持当前版本的 JSONL 诊断日志")

        path = (self.log_dir / file_id).resolve()
        if path.parent != self.log_dir:
            raise ValueError("日志文件超出允许目录")
        if not path.is_file():
            raise FileNotFoundError(f"日志文件不存在: {file_id}")
        return path

    def _get_index(self, file_id: str, force_refresh: bool = False) -> _CachedIndex:
        path = self._resolve_file(file_id)
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(file_id)
            if cached is not None and cached.signature == signature and not force_refresh:
                return cached

            index = self._build_index(path, signature)
            self._cache[file_id] = index
            return index

    def _build_index(self, path: Path, signature: tuple[int, int]) -> _CachedIndex:
        entries: list[dict[str, Any]] = []
        outcomes: set[str] = set()
        stages: set[str] = set()
        call_statuses: set[str] = set()
        failure_kinds: set[str] = set()
        valid_count = 0
        invalid_count = 0
        unsupported_count = 0

        with path.open("rb") as handle:
            line_number = 0
            while True:
                offset = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                line_number += 1
                if not raw.strip():
                    continue

                try:
                    record = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    invalid_count += 1
                    entries.append(self._invalid_entry(line_number, offset, len(raw), str(exc)))
                    outcomes.add("FORMAT_ERROR")
                    failure_kinds.add("invalid_jsonl")
                    continue

                if not isinstance(record, dict) or record.get("schema_version") != CURRENT_SCHEMA_VERSION:
                    unsupported_count += 1
                    continue

                entry = self._summarize_record(record, line_number, offset, len(raw))
                entries.append(entry)
                valid_count += 1
                if entry["outcome"]:
                    outcomes.add(entry["outcome"])
                stages.update(entry["stages"])
                call_statuses.update(entry["call_statuses"])
                failure_kinds.update(entry["failure_kinds"])

        facets = {
            "outcomes": sorted(outcomes),
            "stages": sorted(stages),
            "call_statuses": sorted(call_statuses),
            "failure_kinds": sorted(failure_kinds),
        }
        return _CachedIndex(
            signature=signature,
            entries=entries,
            facets=facets,
            valid_count=valid_count,
            invalid_count=invalid_count,
            unsupported_count=unsupported_count,
        )

    @staticmethod
    def _invalid_entry(line_number: int, offset: int, length: int, error: str) -> dict[str, Any]:
        return {
            "line_number": line_number,
            "offset": offset,
            "length": length,
            "invalid": True,
            "parse_error": error,
            "timestamp": None,
            "file_name": f"第 {line_number} 行",
            "outcome": "FORMAT_ERROR",
            "elapsed_seconds": None,
            "api_call_count": 0,
            "failed_call_count": 0,
            "has_exception": True,
            "exception_type": "JSONDecodeError",
            "exception_message": error,
            "stages": [],
            "call_statuses": [],
            "failure_kinds": ["invalid_jsonl"],
        }

    def _summarize_record(
        self,
        record: dict[str, Any],
        line_number: int,
        offset: int,
        length: int,
    ) -> dict[str, Any]:
        calls = record.get("api_calls") if isinstance(record.get("api_calls"), list) else []
        failed_count = sum(
            1 for call in calls
            if isinstance(call, dict) and call.get("status") not in SUCCESS_CALL_STATUSES
        )
        call_summary = record.get("call_summary") if isinstance(record.get("call_summary"), dict) else {}
        exception = record.get("exception") if isinstance(record.get("exception"), dict) else None
        if exception is None:
            exception = next(
                (
                    call.get("exception")
                    for call in calls
                    if (
                        isinstance(call, dict)
                        and call.get("status") not in SUCCESS_CALL_STATUSES
                        and isinstance(call.get("exception"), dict)
                    )
                ),
                None,
            )
        exception_type, exception_message = self._exception_summary(exception)
        timestamp = record.get("timestamp") if isinstance(record.get("timestamp"), str) else None
        return {
            "line_number": line_number,
            "offset": offset,
            "length": length,
            "invalid": False,
            "parse_error": None,
            "timestamp": timestamp,
            "file_name": str(record.get("file_name") or ""),
            "outcome": str(record.get("outcome") or ""),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "api_call_count": int(call_summary.get("total", len(calls)) or 0),
            "failed_call_count": int(call_summary.get("failed", failed_count) or 0),
            "has_exception": exception is not None,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "stages": sorted({str(call.get("stage")) for call in calls if isinstance(call, dict) and call.get("stage")}),
            "call_statuses": sorted({str(call.get("status")) for call in calls if isinstance(call, dict) and call.get("status")}),
            "failure_kinds": sorted({str(call.get("failure_kind")) for call in calls if isinstance(call, dict) and call.get("failure_kind")}),
        }

    @staticmethod
    def _exception_summary(exception: dict[str, Any] | None) -> tuple[str | None, str | None]:
        if exception is None:
            return None, None
        return (
            str(exception.get("type") or exception.get("exception_type") or "Exception"),
            str(exception.get("message") or exception.get("exception_message") or ""),
        )

    def _normalize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        has_exception = filters.get("has_exception")
        if isinstance(has_exception, str):
            if has_exception.lower() == "true":
                has_exception = True
            elif has_exception.lower() == "false":
                has_exception = False
            else:
                has_exception = None
        return {
            "outcome": str(filters.get("outcome") or "").strip(),
            "stage": str(filters.get("stage") or "").strip(),
            "call_status": str(filters.get("call_status") or "").strip(),
            "failure_kind": str(filters.get("failure_kind") or "").strip(),
            "has_exception": has_exception if isinstance(has_exception, bool) else None,
        }

    def _matches(self, entry: dict[str, Any], filters: dict[str, Any]) -> bool:
        if filters["outcome"] and entry["outcome"] != filters["outcome"]:
            return False
        if filters["stage"] and filters["stage"] not in entry["stages"]:
            return False
        if filters["call_status"] and filters["call_status"] not in entry["call_statuses"]:
            return False
        if filters["failure_kind"] and filters["failure_kind"] not in entry["failure_kinds"]:
            return False
        if filters["has_exception"] is not None and entry["has_exception"] != filters["has_exception"]:
            return False

        return True

    @staticmethod
    def _public_summary(entry: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in entry.items() if key not in {"offset", "length"}}

    @staticmethod
    def _read_entry(path: Path, entry: dict[str, Any]) -> bytes:
        with path.open("rb") as handle:
            return TranslationLogService._read_entry_from_handle(handle, entry)

    @staticmethod
    def _read_entry_from_handle(handle: BinaryIO, entry: dict[str, Any]) -> bytes:
        handle.seek(entry["offset"])
        return handle.read(entry["length"])
