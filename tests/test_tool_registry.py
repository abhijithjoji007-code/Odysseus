from pathlib import Path
import time

from pydantic import BaseModel

from app.services.tool_audit import ToolAudit
from app.tools.models import PermissionLevel, QueryArgs, ToolResult
from app.tools.registry import SecureToolRegistry, ToolDefinition


def test_unknown_tool_is_rejected_and_audited(tmp_path: Path):
    registry = SecureToolRegistry(ToolAudit(tmp_path / "audit.jsonl"))
    result = registry.execute("shell", {"command": "anything"})
    assert not result.success and "Unknown or prohibited" in result.message
    assert "shell" in (tmp_path / "audit.jsonl").read_text()


def test_strict_validation_rejects_extra_fields(tmp_path: Path):
    registry = SecureToolRegistry(ToolAudit(tmp_path / "audit.jsonl"))
    registry.register(ToolDefinition("search", "test", QueryArgs, PermissionLevel.READ_ONLY, lambda a: ToolResult(success=True, message=a.query)))
    result = registry.execute("search", {"query": "notes", "command": "bypass"})
    assert not result.success and "validation" in result.message.lower()


def test_confirmation_is_session_bound_and_single_use(tmp_path: Path):
    calls = []
    registry = SecureToolRegistry(ToolAudit(tmp_path / "audit.jsonl"))
    registry.register(ToolDefinition("startup", "test", QueryArgs, PermissionLevel.CONFIRMATION_REQUIRED, lambda a: (calls.append(a.query) or ToolResult(success=True, message="ran"))))
    pending = registry.execute("startup", {"query": "start"}, "session-a")
    assert pending.confirmation_required and not calls
    assert not registry.confirm("session-b").success
    assert registry.confirm("session-a").success and calls == ["start"]
    assert not registry.confirm("session-a").success


def test_health_exposes_permissions(tmp_path: Path):
    registry = SecureToolRegistry(ToolAudit(tmp_path / "audit.jsonl"))
    registry.register(ToolDefinition("search", "test", QueryArgs, PermissionLevel.READ_ONLY, lambda a: ToolResult(success=True, message="ok")))
    assert registry.health()[0]["permission"] == "read_only"


class EmptyArgs(BaseModel):
    pass


def test_registry_enforces_real_handler_timeout(tmp_path: Path):
    registry = SecureToolRegistry(ToolAudit(tmp_path / "audit.jsonl"))

    def hangs(_):
        time.sleep(0.5)
        return ToolResult(success=True, message="too late")

    registry.register(ToolDefinition("hang", "test", EmptyArgs, PermissionLevel.READ_ONLY, hangs, 0.05))
    started = time.monotonic()
    result = registry.execute("hang", {})
    assert time.monotonic() - started < 0.3
    assert not result.success and "timed out" in result.message
