from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

StepState = Literal["pending", "running", "waiting_input", "waiting_permission", "completed", "failed", "skipped", "cancelled"]
MissionState = Literal["planned", "running", "waiting_input", "waiting_permission", "completed", "failed", "cancelled"]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class MissionStep(BaseModel):
    id: str
    title: str
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: StepState = "pending"
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    started_at: str | None = None
    completed_at: str | None = None

class MissionRecord(BaseModel):
    id: str
    session_id: str
    objective: str
    workflow: str
    title: str
    status: MissionState = "planned"
    progress: int = 0
    steps: list[MissionStep]
    prompt: str = ""
    choices: list[dict[str, Any]] = Field(default_factory=list)
    final_report: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
