from __future__ import annotations

import secrets
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Type

from pydantic import BaseModel, ValidationError

from app.services.tool_audit import ToolAudit
from app.tools.models import PermissionLevel, ToolResult


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    args_model: Type[BaseModel]
    permission: PermissionLevel
    handler: Callable[[BaseModel], ToolResult]
    timeout_seconds: float = 10.0
    available: Callable[[], bool] = lambda: True


class SecureToolRegistry:
    """Single validated boundary for every desktop tool execution."""

    def __init__(self, audit: ToolAudit, confirmation_ttl: float = 300.0) -> None:
        self.audit = audit
        self.confirmation_ttl = confirmation_ttl
        self._tools: dict[str, ToolDefinition] = {}
        self._pending: dict[str, tuple[str, str, BaseModel, float]] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def _audit(self, name: str, arguments: dict, result: ToolResult, outcome: str) -> None:
        if hasattr(self.audit, "record_registry"):
            self.audit.record_registry(name, arguments, result, outcome)
        else:
            self.audit.record(name, arguments, result.success, result.message)

    def execute(self, name: str, arguments: dict, session_id: str = "default", confirmed: bool = False) -> ToolResult:
        definition = self._tools.get(name)
        if not definition:
            result = ToolResult(success=False, message=f"Unknown or prohibited tool: {name}", tool=name)
            self._audit(name, arguments, result, "rejected")
            return result
        try:
            parsed = definition.args_model.model_validate(arguments)
        except ValidationError as exc:
            result = ToolResult(success=False, message="Tool input validation failed.", data={"errors": exc.errors(include_url=False)}, tool=name)
            self._audit(name, arguments, result, "validation_failed")
            return result
        if not definition.available():
            result = ToolResult(success=False, message=f"Tool '{name}' is currently unavailable.", tool=name)
            self._audit(name, arguments, result, "unavailable")
            return result
        if definition.permission == PermissionLevel.CONFIRMATION_REQUIRED and not confirmed:
            token = secrets.token_urlsafe(18)
            self._pending[session_id] = (token, name, parsed, time.monotonic())
            result = ToolResult(success=False, message=f"Confirmation required before running {name}.", data={"confirmation_token": token}, tool=name, confirmation_required=True)
            self._audit(name, arguments, result, "confirmation_required")
            return result
        return self._invoke(definition, parsed)

    def confirm(self, session_id: str, token: str | None = None) -> ToolResult:
        pending = self._pending.pop(session_id, None)
        if not pending:
            return ToolResult(success=False, message="There is no pending tool action to confirm.")
        expected, name, parsed, created = pending
        if time.monotonic() - created > self.confirmation_ttl:
            return ToolResult(success=False, message="The tool confirmation expired.", tool=name)
        if token is not None and not secrets.compare_digest(token, expected):
            return ToolResult(success=False, message="The confirmation token is invalid.", tool=name)
        return self._invoke(self._tools[name], parsed)

    def cancel(self, session_id: str) -> bool:
        return self._pending.pop(session_id, None) is not None

    def _invoke(self, definition: ToolDefinition, parsed: BaseModel) -> ToolResult:
        # Measuring elapsed time after a handler returns does not enforce a
        # timeout: a blocked filesystem or network call could leave a mission
        # in "running" forever.  Execute in a daemon worker and stop waiting at
        # the registered deadline.  The process can still exit even if an OS
        # call remains blocked in that worker.
        results: queue.Queue[ToolResult] = queue.Queue(maxsize=1)

        def call_handler() -> None:
            try:
                results.put(definition.handler(parsed), block=False)
            except Exception as exc:
                results.put(
                    ToolResult(success=False, message=f"Tool '{definition.name}' failed safely: {exc}"),
                    block=False,
                )

        threading.Thread(target=call_handler, daemon=True, name=f"odysseus-tool-{definition.name}").start()
        try:
            result = results.get(timeout=definition.timeout_seconds)
        except queue.Empty:
            result = ToolResult(
                success=False,
                message=(
                    f"Tool '{definition.name}' timed out after "
                    f"{definition.timeout_seconds:g} seconds. Check the configured search folders, "
                    "network connection, or AI diagnostics, then retry."
                ),
            )
        result.tool = definition.name
        self._audit(definition.name, parsed.model_dump(), result, "executed")
        return result

    def health(self) -> list[dict[str, object]]:
        return [{"name": item.name, "permission": item.permission.value, "available": bool(item.available()), "timeout_seconds": item.timeout_seconds} for item in self._tools.values()]
