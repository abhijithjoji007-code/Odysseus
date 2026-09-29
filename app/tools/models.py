from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    LOCAL_ACTION = "local_action"
    CONFIRMATION_REQUIRED = "confirmation_required"


class ToolResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    tool: str = ""
    confirmation_required: bool = False


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QueryArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=500)


class PathArgs(StrictArgs):
    path: str = Field(min_length=1, max_length=4096)

class StudyMaterialArgs(StrictArgs):
    text: str = Field(min_length=1, max_length=80000)
    objective: str = Field(min_length=1, max_length=4000)

class ProjectSessionArgs(StrictArgs):
    project: str = Field(min_length=1, max_length=300)
    report: str = Field(min_length=1, max_length=4000)


class AppArgs(StrictArgs):
    name: str = Field(min_length=1, max_length=300)
    target: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1, max_length=100)
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class ProjectArgs(StrictArgs):
    name: str = Field(min_length=1, max_length=300)
    path: str = Field(min_length=1, max_length=4096)
    project_type: str = Field(default="Project folder", max_length=300)
    markers: list[str] = Field(default_factory=list, max_length=30)
    source: str = Field(default="discovered", max_length=100)
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class RegisterProjectArgs(StrictArgs):
    alias: str = Field(min_length=1, max_length=200)
    folder: str = Field(min_length=1, max_length=4096)


class UpdateProjectArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=300)
    field: str = Field(pattern="^(notes|editor|startup_command|localhost_url)$")
    value: str = Field(min_length=1, max_length=2000)
