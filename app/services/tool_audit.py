from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.models import ToolResult


class ToolAudit:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, tool: str, inputs: dict[str, Any], success: bool, message: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "inputs": inputs,
            "success": success,
            "message": message,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record_registry(self, tool: str, inputs: dict[str, Any], result: "ToolResult", outcome: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(), "event": "tool_registry",
            "tool": tool, "inputs": inputs, "permission_outcome": outcome,
            "success": result.success, "message": result.message,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
