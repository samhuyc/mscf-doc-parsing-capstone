"""Bounded exact-match topic memory. No API clients, report retrieval, or task execution."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from json_storage import JsonStorageError, read_json_record, write_json_record

MEMORY_DIR = Path(__file__).resolve().parent / "artifacts" / "research_memory"
MAX_RECORD_BYTES = 4096
MAX_TOPIC_RECORDS = 20
MAX_MEMORY_RESULTS = 3
MAX_MEMORY_CONTEXT_CHARS = 1800
STALE_AFTER_DAYS = 7


class MemoryStoreError(ValueError):
    """Controlled, credential-free messages only."""


class MemoryKey(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    company: Annotated[str, Field(pattern=r"^[A-Z]{1,10}$")]
    metric: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    year: Annotated[int, Field(ge=2000, le=2099)]
    quarter: Annotated[int, Field(ge=1, le=4)]


class SourceLocation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    url: Annotated[str, Field(max_length=512)]
    page: Annotated[int, Field(ge=1, le=10000)]

    @field_validator("url")
    @classmethod
    def check_public_locator(cls, value):
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or any(char.isspace() or ord(char) < 32 for char in value)):
            raise ValueError("Only credential-free HTTPS source locators are supported.")
        return value


class MemoryRecord(MemoryKey):
    schema_version: Literal["1"]
    source: SourceLocation
    last_verified_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]
    snapshot_task_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]

    @field_validator("last_verified_at")
    @classmethod
    def check_date(cls, value):
        parse_time(value)
        return value


class MemoryMatch(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    context_kind: Literal["historical_context"]
    record: MemoryRecord
    is_stale: bool
    stale_reason: Literal["age_exceeded", "future_timestamp", "within_window"]
    requires_revalidation: Literal[True]


def parse_time(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(value):
    return MemoryKey.model_validate({name: getattr(value, name) for name in MemoryKey.model_fields})


def _topic_dir(directory, key):
    # All components have already passed strict type/range/pattern checks.
    return Path(directory) / key.company / key.metric / f"{key.year}Q{key.quarter}"


def _record_paths(directory):
    paths = []
    try:
        for path in directory.iterdir():
            if path.suffix != ".json":
                continue  # Interrupted .tmp files are not published records.
            paths.append(path)
            if len(paths) > MAX_TOPIC_RECORDS:
                raise MemoryStoreError("同一主题超过 20 条记录，已停止读取；请先整理记录。")
    except FileNotFoundError:
        return []
    except OSError:
        raise MemoryStoreError("Memory 目录不可读。") from None
    return sorted(paths)


def save_memory(record: MemoryRecord, directory=MEMORY_DIR):
    """Save one topic/task record atomically. No raw conversation, amount or instructions."""
    try:
        # Revalidate even if the caller used model_construct/model_copy to bypass checks.
        record = MemoryRecord.model_validate(record.model_dump())
        folder = _topic_dir(directory, _key(record))
        target = folder / f"{record.snapshot_task_id}.json"
        paths = _record_paths(folder)
        if target not in paths and len(paths) >= MAX_TOPIC_RECORDS:
            raise MemoryStoreError("同一主题最多保存 20 条记录；未覆盖其他任务。")
        return write_json_record(record, target, MAX_RECORD_BYTES)
    except (AttributeError, ValueError) as error:
        if isinstance(error, MemoryStoreError):
            raise
        raise MemoryStoreError("Memory 未通过校验或写入失败；未回显数据。") from None


def search_memory(company, metric, year, quarter, *, directory=MEMORY_DIR, limit=MAX_MEMORY_RESULTS, now=None):
    """Read at most 20 records from the exact topic; return at most 3 historical matches."""
    try:
        key = MemoryKey(company=company, metric=metric, year=year, quarter=quarter)
        if type(limit) is not int or not 1 <= limit <= MAX_MEMORY_RESULTS:
            raise ValueError("Invalid result limit.")
        checked_now = now if now is not None else datetime.now(timezone.utc)
        if checked_now.tzinfo is None or checked_now.utcoffset() is None:
            raise ValueError("Use timezone-aware UTC timestamps.")
        matches = []
        for path in _record_paths(_topic_dir(directory, key)):
            record = read_json_record(path, MemoryRecord, MAX_RECORD_BYTES)
            if _key(record) != key or path.stem != record.snapshot_task_id:
                raise ValueError("Topic or task ID does not match storage location.")
            age = checked_now - parse_time(record.last_verified_at)
            reason = ("future_timestamp" if age < timedelta(0) else
                      "age_exceeded" if age >= timedelta(days=STALE_AFTER_DAYS) else "within_window")
            matches.append(MemoryMatch(context_kind="historical_context", record=record,
                                       is_stale=reason != "within_window", stale_reason=reason,
                                       requires_revalidation=True))
        # Prefer non-stale records, then newest verification; tie-break by task ID.
        matches.sort(key=lambda match: (match.is_stale, -parse_time(match.record.last_verified_at).timestamp(),
                                        match.record.snapshot_task_id))
        return matches[:limit]
    except (ValueError, AttributeError, TypeError):
        raise MemoryStoreError("Memory 查询失败：参数、记录、版本或存储位置未通过校验。") from None


def memory_context_items(matches, query):
    """Bounded projection for Context Builder; never load snapshots or create evidence."""
    try:
        if not isinstance(matches, (list, tuple)):
            raise ValueError("Expected a bounded sequence.")
        key = _key(query)
        items = []
        for match in matches[:MAX_MEMORY_RESULTS]:
            match = MemoryMatch.model_validate(match.model_dump())
            if _key(match.record) != key:
                continue
            item = match.model_dump()
            if len(json.dumps([*items, item], ensure_ascii=False)) > MAX_MEMORY_CONTEXT_CHARS:
                break  # Drop complete records; do not truncate URLs or flags.
            items.append(item)
        return items
    except (ValueError, AttributeError, TypeError):
        raise MemoryStoreError("历史 Context 未通过校验。") from None
