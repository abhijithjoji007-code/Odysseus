from __future__ import annotations

import time
from pathlib import Path

from app.config import ASSISTANT_NAME, DATABASE_PATH, DATA_DIR, PROJECT_SCAN_PATH, FILE_SEARCH_ROOTS, PROJECT_SEARCH_ROOTS
from app.schemas import AssistantResponse
from app.services.app_launcher import AppLauncher
from app.services.browser_tools import open_search
from app.services.intent_router import Intent, parse_intent
from app.services.llm import GeminiService
from app.services.memory import MemoryStore
from app.services.mission_engine import MissionEngine
from app.services.project_intelligence import ProjectAnalyzer, deterministic_summary
from app.services.system_tools import current_time_message, system_summary
from app.services.file_finder import FileFinder, FileMatch
from app.services.project_registry import ProjectRegistry
from app.services.tool_audit import ToolAudit
from app.tools.definitions import build_tool_registry
from app.services.document_reader import DocumentReader
from app.missions.runner import MissionRunner
from app.missions.store import MissionStore


class OdysseusAssistant:
    def __init__(self) -> None:
        self.memory = MemoryStore(DATABASE_PATH)
        self.launcher = AppLauncher()
        self.llm = GeminiService()
        self.missions = MissionEngine(DATA_DIR / "missions.json")
        self.project_analyzer = ProjectAnalyzer(PROJECT_SCAN_PATH)
        self._project_snapshot = None
        self.file_finder = FileFinder(FILE_SEARCH_ROOTS + [PROJECT_SCAN_PATH])
        default_project_roots = [Path.home() / "Desktop", Path.home() / "Documents", PROJECT_SCAN_PATH]
        self.projects = ProjectRegistry(DATA_DIR / "projects.json", PROJECT_SEARCH_ROOTS + default_project_roots)
        self.audit = ToolAudit(DATA_DIR / "tool_audit.jsonl")
        self.document_reader = DocumentReader(FILE_SEARCH_ROOTS + [PROJECT_SCAN_PATH])
        self.tools = build_tool_registry(self.file_finder, self.launcher, self.projects, self.audit, self.document_reader, self.llm)
        self.mission_runner = MissionRunner(MissionStore(DATA_DIR / "mission_history_v3.json"), self.tools)
        self._active_missions: dict[str, str] = {}
        self._tool_service_ids = (id(self.file_finder), id(self.launcher), id(self.projects))
        # Pending choices are isolated per browser conversation and expire so a
        # later number cannot accidentally open an old result.
        self._pending_files: dict[str, tuple[list, float]] = {}
        self._pending_apps: dict[str, tuple[list, float]] = {}
        self._pending_projects: dict[str, tuple[list, float]] = {}
        self._pending_startup: dict[str, tuple[object, float]] = {}

    def handle(self, message: str, session_id: str = "default") -> AssistantResponse:
        service_ids = (id(self.file_finder), id(self.launcher), id(self.projects))
        if service_ids != self._tool_service_ids:
            self.tools = build_tool_registry(self.file_finder, self.launcher, self.projects, self.audit, self.document_reader, self.llm)
            self.mission_runner.registry = self.tools
            self._tool_service_ids = service_ids
        clean_message = message.strip()
        active_id = self._active_missions.get(session_id)
        active = self.mission_runner.get(active_id, session_id) if active_id else None
        if active and active.status in {"waiting_input", "waiting_permission"}:
            updated = self.mission_runner.respond(active.id, session_id, clean_message)
            if updated:
                return AssistantResponse(reply=updated.prompt or "Mission resumed. Live progress is shown in the mission panel.", action="mission_resume", success=updated.status != "cancelled", data={"mission_id": updated.id})
        elif active and active.status in {"completed", "failed", "cancelled"}:
            self._active_missions.pop(session_id, None)
        pending = self._pending_files.get(session_id)
        pending_apps = self._pending_apps.get(session_id)
        pending_projects = self._pending_projects.get(session_id)
        pending_startup = self._pending_startup.get(session_id)
        if pending and time.monotonic() - pending[1] > 600:
            self._pending_files.pop(session_id, None)
            pending = None
        if pending_apps and time.monotonic() - pending_apps[1] > 600:
            self._pending_apps.pop(session_id, None)
            pending_apps = None
        if pending_projects and time.monotonic() - pending_projects[1] > 600:
            self._pending_projects.pop(session_id, None)
            pending_projects = None
        if pending_startup and time.monotonic() - pending_startup[1] > 300:
            self._pending_startup.pop(session_id, None)
            pending_startup = None

        if pending_startup and clean_message.lower() in {"yes", "confirm", "run it", "start it"}:
            candidate = pending_startup[0]
            self._pending_startup.pop(session_id, None)
            result = self.tools.confirm(session_id)
            return AssistantResponse(reply=result.message, action="project_startup", success=result.success, data=result.data)
        if pending_startup and clean_message.lower() in {"no", "cancel", "do not run", "don't run"}:
            self._pending_startup.pop(session_id, None)
            self.tools.cancel(session_id)
            return AssistantResponse(reply="Project startup cancelled. No command was run.", action="cancel_project_startup")

        if clean_message.lower() in {"cancel", "cancel file", "cancel app", "cancel project", "never mind", "nevermind"} and (pending or pending_apps or pending_projects):
            action = "cancel_project_selection" if pending_projects else ("cancel_file_selection" if pending and not pending_apps else "cancel_app_selection")
            self._pending_files.pop(session_id, None)
            self._pending_apps.pop(session_id, None)
            self._pending_projects.pop(session_id, None)
            return AssistantResponse(reply="Selection cancelled.", action=action)

        # A numbered response resolves the most recent ambiguous file search.
        if pending and clean_message.isdigit():
            choice = int(clean_message) - 1
            choices = pending[0]
            if 0 <= choice < len(choices):
                selected = choices[choice]
                self._pending_files.pop(session_id, None)
                result = self.tools.execute("open_file", {"path": str(selected.path)}, session_id)
                return AssistantResponse(reply=result.message, action="open_file", success=result.success, data=result.data)
            return AssistantResponse(
                reply=f"Please choose a number from 1 to {len(choices)}, or type Cancel.",
                action="file_selection",
                success=False,
            )

        if pending_apps and clean_message.isdigit():
            choice = int(clean_message) - 1
            choices = pending_apps[0]
            if 0 <= choice < len(choices):
                selected = choices[choice]
                self._pending_apps.pop(session_id, None)
                result = self.tools.execute("open_application", {"name": selected.name, "target": selected.target, "source": selected.source, "score": selected.score}, session_id)
                return AssistantResponse(reply=result.message, action="open_app", success=result.success, data=result.data)
            return AssistantResponse(
                reply=f"Please choose an application from 1 to {len(choices)}, or type Cancel.",
                action="app_selection",
                success=False,
            )

        if pending_projects and clean_message.isdigit():
            choice = int(clean_message) - 1
            choices = pending_projects[0]
            if 0 <= choice < len(choices):
                selected = choices[choice]
                self._pending_projects.pop(session_id, None)
                result = self.tools.execute("open_project", selected.to_dict(), session_id)
                return AssistantResponse(reply=result.message, action="open_project", success=result.success, data=result.data)
            return AssistantResponse(
                reply=f"Please choose a project from 1 to {len(choices)}, or type Cancel.",
                action="project_selection",
                success=False,
            )

        # Deterministic commands take precedence over broad mission keywords.
        # This ensures commands such as “Open my latest resume” reach FileFinder.
        planned = self.mission_runner.start(clean_message, session_id)
        if planned:
            self._active_missions[session_id] = planned.id
            return AssistantResponse(reply="Mission planned and started. Progress now reflects real tool execution.", action="mission_started", data={"mission_id": planned.id})

        parsed = parse_intent(clean_message)
        template = self.missions.detect(clean_message) if parsed.intent == Intent.CHAT else None
        if template:
            if template.kind == "project_intelligence":
                self._project_snapshot = None
            mission = self.missions.plan(clean_message, template)
            mission = self.missions.execute(
                mission,
                llm_reply=lambda prompt: self.llm.reply(prompt, self._memory_text()),
                open_vscode=lambda: self._open_app_via_tools("vscode", session_id),
                system_summary=system_summary,
                memory_context=self._memory_text,
                save_memory=lambda content: self.memory.add(content),
                project_scan=self._scan_project,
                project_review=self._review_project,
            )
            return AssistantResponse(
                reply=self._mission_reply(mission),
                action="mission",
                success=mission.status == "completed",
                mission=mission,
                data={"mission_id": mission.id},
            )

        if parsed.intent == Intent.FIND_FILE:
            self._pending_files.pop(session_id, None)
            self._pending_apps.pop(session_id, None)
            search_result = self.tools.execute("search_files", {"query": parsed.argument}, session_id)
            matches = [FileMatch(Path(item["path"]), float(item.get("score", 0)), time.time()) for item in search_result.data.get("matches", [])]
            if not matches:
                reply = "I could not find a matching file in Desktop, Documents, Downloads, the configured project folder, or extra search roots."
                self.audit.record("search_files", {"query": parsed.argument}, False, reply)
                return AssistantResponse(reply=reply, action="find_file", success=False)
            wants_open = parsed.argument.lower().startswith("open ")
            confident = len(matches) == 1 or (matches[0].score >= 0.72 and (len(matches) == 1 or matches[0].score - matches[1].score >= 0.15))
            if wants_open and confident:
                result = self.tools.execute("open_file", {"path": str(matches[0].path)}, session_id)
                return AssistantResponse(reply=result.message, action="open_file", success=result.success, data={"match": matches[0].to_dict()})
            # Every displayed numbered list must be selectable. Previously,
            # choices were saved only for commands beginning with "open", so
            # replying "1" after a "find" command fell through to chat.
            self._pending_files[session_id] = (matches[:5], time.monotonic())
            lines = [f"{index}. {item.path.name} — {item.path.parent}" for index, item in enumerate(matches[:5], 1)]
            reply = "I found these matches:\n" + "\n".join(lines)
            reply += "\n\nReply with the number of the file to open, or type Cancel."
            self.audit.record("search_files", {"query": parsed.argument}, True, f"Found {len(matches)} matches")
            return AssistantResponse(reply=reply, action="find_file", data={"matches": [m.to_dict() for m in matches[:5]]})
        if parsed.intent == Intent.REGISTER_PROJECT:
            alias, folder = parsed.argument.split("|", 1)
            if folder.lower() in {"this folder", "current folder", "."}:
                folder = str(PROJECT_SCAN_PATH)
            result = self.tools.execute("register_project", {"alias": alias, "folder": folder}, session_id)
            return AssistantResponse(reply=result.message, action="register_project", success=result.success)
        if parsed.intent in {Intent.PROJECT_STATUS, Intent.PROJECT_NOTE, Intent.SET_PROJECT_EDITOR, Intent.SET_PROJECT_STARTUP, Intent.SET_PROJECT_URL}:
            if parsed.intent == Intent.PROJECT_STATUS:
                query = parsed.argument
                value = ""
            else:
                query, value = parsed.argument.split("|", 1)
            matches = self.projects.find_matches(query)
            if not matches:
                self.projects.refresh_discovery()
                matches = self.projects.find_matches(query)
            if not matches:
                return AssistantResponse(reply=f"I could not find a project matching '{query}'.", action=parsed.intent.value, success=False)
            if parsed.intent == Intent.PROJECT_STATUS:
                context_result = self.tools.execute("project_status", matches[0].to_dict(), session_id)
                context = context_result.data["context"]
                git = context["git"]
                git_text = "not a Git repository" if not git.get("repository") else f"branch {git.get('branch', 'unknown')}, {git.get('changes', 0)} changed files"
                notes = context.get("notes", [])
                note_text = "; ".join(item.get("text", "") for item in notes) if notes else "none"
                reply = (
                    f"Project: {context['name']} ({context['project_type']})\n"
                    f"Path: {context['path']}\nGit: {git_text}\n"
                    f"README: {context.get('readme') or 'not found'}\n"
                    f"TODO files: {', '.join(context.get('todo_files', [])) or 'none'}\n"
                    f"Editor: {context.get('editor') or 'auto'}\nRecent notes: {note_text}"
                )
                return AssistantResponse(reply=reply, action="project_status", data={"context": context})
            field = {
                Intent.PROJECT_NOTE: "notes", Intent.SET_PROJECT_EDITOR: "editor",
                Intent.SET_PROJECT_STARTUP: "startup_command", Intent.SET_PROJECT_URL: "localhost_url",
            }[parsed.intent]
            result = self.tools.execute("update_project", {"query": query, "field": field, "value": value}, session_id)
            return AssistantResponse(reply=result.message, action=parsed.intent.value, success=result.success)
        if parsed.intent == Intent.OPEN_PROJECT:
            self._pending_files.pop(session_id, None)
            self._pending_apps.pop(session_id, None)
            self._pending_projects.pop(session_id, None)
            matches = self.projects.find_matches(parsed.argument)
            if not matches:
                matches = self.projects.find_matches(parsed.argument) if self.projects.refresh_discovery() else []
            if not matches:
                reply = f"I could not find a project matching '{parsed.argument}'. Add its parent folder to PROJECT_SEARCH_ROOTS or register it by path."
                self.audit.record("find_project", {"query": parsed.argument}, False, reply)
                return AssistantResponse(reply=reply, action="open_project", success=False)
            confident = len(matches) == 1 or matches[0].score >= 0.95 or matches[0].score - matches[1].score >= 0.15
            if confident:
                result = self.tools.execute("open_project", matches[0].to_dict(), session_id)
                success, reply = result.success, result.message
                if success and clean_message.lower().startswith("continue ") and hasattr(self.projects, "project_context"):
                    context = self.tools.execute("project_status", matches[0].to_dict(), session_id).data.get("context", {})
                    command, url = self.projects.startup_details(matches[0])
                    git = context.get("git", {})
                    context_line = "Git is not configured." if not git.get("repository") else f"Git: {git.get('branch', 'unknown')} branch with {git.get('changes', 0)} changed files."
                    reply += f"\n{context_line} README: {context.get('readme') or 'not found'}. TODO files: {len(context.get('todo_files', []))}."
                    if context.get("notes"):
                        reply += f" Latest note: {context['notes'][-1].get('text', '')}"
                    if command:
                        self._pending_startup[session_id] = (matches[0], time.monotonic())
                        self.tools.execute("run_project_startup", matches[0].to_dict(), session_id)
                        reply += f"\nConfigured startup command: {command}. Reply Confirm to run it, or Cancel."
                    if url:
                        reply += f"\nLocal URL: {url}"
                return AssistantResponse(reply=reply, action="open_project", success=success, data={"project": matches[0].to_dict()})
            self._pending_projects[session_id] = (matches, time.monotonic())
            lines = [f"{index}. {item.name} — {item.project_type} — {item.path}" for index, item in enumerate(matches, 1)]
            reply = "I found multiple project matches:\n" + "\n".join(lines)
            reply += "\n\nReply with the project number to open, or type Cancel."
            return AssistantResponse(reply=reply, action="project_selection", data={"matches": [item.to_dict() for item in matches]})
        if parsed.intent == Intent.LIST_PROJECTS:
            catalog = self.projects.refresh_discovery()
            if not catalog:
                reply = "No projects were found in the configured project search roots."
            else:
                reply = "Discovered projects:\n" + "\n".join(f"- {item.name} ({item.project_type}): {item.path}" for item in catalog[:20])
            return AssistantResponse(reply=reply, action="list_projects", data={"projects": [item.to_dict() for item in catalog[:20]]})
        if parsed.intent == Intent.OPEN_APP:
            self._pending_apps.pop(session_id, None)
            self._pending_files.pop(session_id, None)
            matches = self.launcher.find_matches(parsed.argument)
            if not matches:
                self.launcher.refresh_discovery()
                matches = self.launcher.find_matches(parsed.argument)
            if not matches:
                reply = f"I could not find an installed application matching '{parsed.argument}'. Try its full Start Menu name or add an alias in app/data/apps.json."
                self.audit.record("open_application", {"name": parsed.argument}, False, reply)
                return AssistantResponse(reply=reply, action="open_app", success=False)
            if len(matches) == 1 or matches[0].score >= 0.95 or matches[0].score - matches[1].score >= 0.12:
                selected = matches[0]
                result = self.tools.execute("open_application", {"name": selected.name, "target": selected.target, "source": selected.source, "score": selected.score}, session_id)
                return AssistantResponse(reply=result.message, action="open_app", success=result.success, data=result.data)
            self._pending_apps[session_id] = (matches, time.monotonic())
            lines = [f"{index}. {item.name} ({item.source.replace('_', ' ')})" for index, item in enumerate(matches, 1)]
            reply = "I found multiple application matches:\n" + "\n".join(lines)
            reply += "\n\nReply with the application number to open, or type Cancel."
            return AssistantResponse(reply=reply, action="app_selection", data={"matches": [item.to_dict() for item in matches]})
        if parsed.intent == Intent.WEB_SEARCH:
            return AssistantResponse(reply=open_search(parsed.argument), action="web_search")
        if parsed.intent == Intent.REMEMBER:
            item = self.memory.add(parsed.argument)
            return AssistantResponse(reply=f"Memory {item.id} saved.", action="remember", data={"id": item.id})
        if parsed.intent == Intent.LIST_MEMORY:
            items = self.memory.list()
            reply = "I do not have any saved memories yet." if not items else "Saved memories:\n" + "\n".join(f"{i.id}. {i.content}" for i in items)
            return AssistantResponse(reply=reply, action="list_memory")
        if parsed.intent == Intent.FORGET_MEMORY:
            memory_id = int(parsed.argument)
            deleted = self.memory.delete(memory_id)
            return AssistantResponse(reply=f"Memory {memory_id} {'deleted' if deleted else 'was not found'}.", action="forget_memory", success=deleted)
        if parsed.intent == Intent.TIME:
            return AssistantResponse(reply=current_time_message(), action="time")
        if parsed.intent == Intent.SYSTEM_INFO:
            return AssistantResponse(reply=system_summary(), action="system_info")
        if parsed.intent == Intent.HELP:
            apps = ", ".join(self.launcher.available_apps())
            return AssistantResponse(
                reply=(
                    f"I am {ASSISTANT_NAME}. I can run Project Intelligence, study, biotechnology research, "
                    f"career preparation, and developer workspace missions. I can also open approved apps, "
                    f"search the web, remember facts, report system status, and answer through Gemini. "
                    f"I can intelligently find and open files, discover Start Menu applications, register and reopen projects, "
                    f"run Project Intelligence and other missions, search the web, remember facts, and answer through Gemini. "
                    f"Known apps include: {apps[:600]}."
                ),
                action="help",
            )
        return AssistantResponse(reply=self.llm.reply(parsed.argument, self._memory_text()), action="chat")

    def _memory_text(self) -> list[str]:
        return [item.content for item in self.memory.list(limit=10)]

    def _open_app_via_tools(self, query: str, session_id: str) -> tuple[bool, str]:
        discovery = self.tools.execute("discover_apps", {"query": query}, session_id)
        matches = discovery.data.get("matches", [])
        if not matches:
            return False, discovery.message
        result = self.tools.execute("open_application", matches[0], session_id)
        return result.success, result.message

    @staticmethod
    def _mission_reply(mission) -> str:
        state = "completed" if mission.status == "completed" else "stopped"
        return f"Mission {state}: {mission.title}\n\n{mission.output}"

    def _scan_project(self):
        if self._project_snapshot is None:
            self._project_snapshot = self.project_analyzer.scan()
        return self._project_snapshot, deterministic_summary(self._project_snapshot)

    def _review_project(self, snapshot) -> str:
        prompt = (
            "You are the Project Intelligence Advisor inside Odysseus. Review only the repository snapshot below. "
            "Do not claim you executed code or inspected files not shown. Produce: (1) architecture interpretation, "
            "(2) three strongest aspects, (3) five ranked improvements with concrete file-oriented next actions, "
            "and (4) a portfolio-readiness score out of 10 with a short justification. Keep it under 700 words.\n\n"
            + snapshot.compact_for_llm()
        )
        return self.llm.reply(prompt, self._memory_text())
