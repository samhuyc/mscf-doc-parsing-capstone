"""Versioned, local summary records. Loading never creates an executable AgentState."""

import os
from pathlib import Path
from typing import Annotated, Literal, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from json_storage import JsonStorageError, read_json_record, write_json_record

if TYPE_CHECKING:
    from api_demo import AgentState

SCHEMA_VERSION = "1"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "artifacts" / "state_snapshots"
MAX_SNAPSHOT_BYTES = 64 * 1024
NonnegativeInt = Annotated[int, Field(ge=0)]
Stage = Literal[
    "initialization", "budget_check", "api_request", "response_validation",
    "final_validation", "tool_validation", "tool_execution", "state_update", "finished",
]


class SnapshotError(ValueError):
    """A safe message that never echoes file contents or arbitrary exceptions."""


class TokenUsageSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    input_tokens: NonnegativeInt
    output_tokens: NonnegativeInt
    total_tokens: NonnegativeInt

    @model_validator(mode="after")
    def check_total(self):
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Token counts are inconsistent.")
        return self


class StateSnapshot(BaseModel):
    """Read-only summary, deliberately excluding conversation, evidence and credentials."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["1"]
    task_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    user_question: Annotated[str, Field(max_length=1000)]
    status: Literal["pending", "running", "completed", "failed"]
    stage: Stage
    tool_call_count: NonnegativeInt
    api_request_count: NonnegativeInt
    token_usage: TokenUsageSnapshot
    final_answer: Annotated[str, Field(min_length=1, max_length=8000)] | None
    failure_stage: Stage | None

    @model_validator(mode="after")
    def check_outcome(self):
        if self.status == "completed":
            if self.final_answer is None or self.stage != "finished":
                raise ValueError("Completed tasks need a final answer and finished stage.")
        elif self.final_answer is not None or self.stage == "finished":
            raise ValueError("Unfinished tasks cannot have a final answer or finished stage.")
        if self.status == "failed":
            if self.failure_stage is None or self.failure_stage != self.stage:
                raise ValueError("Failed tasks need a matching failure stage.")
        elif self.failure_stage is not None:
            raise ValueError("Only failed tasks have a failure stage.")
        return self


def save_state_snapshot(state: "AgentState", directory: Path = SNAPSHOT_DIR) -> Path:
    """Explicitly save approved summary fields; never serialize the entire state.

    The demo's fixed questions and validated public-report answers are approved
    summary data. Callers extending the demo must review these two text fields
    before persisting private questions or answers. Raw errors are never saved.
    """
    try:
        snapshot = StateSnapshot.model_validate({
            "schema_version": SCHEMA_VERSION,
            "task_id": state.task_id,
            "user_question": state.user_question,
            "status": state.status,
            "stage": state.stage,
            "tool_call_count": state.tool_call_count,
            "api_request_count": state.api_request_count,
            "token_usage": {
                "input_tokens": state.input_tokens,
                "output_tokens": state.output_tokens,
                "total_tokens": state.total_tokens,
            },
            "final_answer": state.final_answer,
            "failure_stage": state.failure_stage,
        })
    except (ValidationError, AttributeError):
        raise SnapshotError("State 摘要未通过校验，未写入文件。") from None
    target = Path(directory) / f"{snapshot.task_id}.json"
    try:
        return write_json_record(snapshot, target, MAX_SNAPSHOT_BYTES)
    except JsonStorageError as error:
        raise SnapshotError("Snapshot：" + str(error)) from None


def load_state_snapshot(path: Path) -> StateSnapshot:
    """Validate and read a summary only. No client, tools, or Agent Loop are called."""
    try:
        return read_json_record(path, StateSnapshot, MAX_SNAPSHOT_BYTES)
    except JsonStorageError:
        # ValidationError is a ValueError. Do not echo it: it includes input data.
        raise SnapshotError("无法读取 Snapshot：文件损坏、Schema 不符、版本不兼容或文件不可读。") from None
