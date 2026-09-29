from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class MissionStep(BaseModel):
    id: str
    agent: str
    title: str
    detail: str
    status: Literal["pending", "running", "completed", "failed", "waiting"] = "pending"


class Mission(BaseModel):
    id: str
    title: str
    objective: str
    kind: str
    status: Literal["planned", "running", "completed", "failed"] = "planned"
    progress: int = 0
    steps: list[MissionStep] = Field(default_factory=list)
    output: str = ""


class AssistantResponse(BaseModel):
    reply: str
    action: str = "chat"
    success: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    mission: Mission | None = None
