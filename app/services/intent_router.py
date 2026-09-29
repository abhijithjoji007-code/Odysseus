from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    OPEN_APP = "open_app"
    FIND_FILE = "find_file"
    REGISTER_PROJECT = "register_project"
    OPEN_PROJECT = "open_project"
    LIST_PROJECTS = "list_projects"
    PROJECT_STATUS = "project_status"
    PROJECT_NOTE = "project_note"
    SET_PROJECT_EDITOR = "set_project_editor"
    SET_PROJECT_STARTUP = "set_project_startup"
    SET_PROJECT_URL = "set_project_url"
    WEB_SEARCH = "web_search"
    REMEMBER = "remember"
    LIST_MEMORY = "list_memory"
    FORGET_MEMORY = "forget_memory"
    TIME = "time"
    SYSTEM_INFO = "system_info"
    HELP = "help"
    CHAT = "chat"


@dataclass(frozen=True)
class ParsedIntent:
    intent: Intent
    argument: str = ""


def parse_intent(message: str) -> ParsedIntent:
    text = " ".join(message.strip().split())
    lower = text.lower()

    register = re.match(r"^register\s+(.+?)\s+as\s+(?:my\s+)?(.+?)\s+project$", text, re.IGNORECASE)
    if register:
        return ParsedIntent(Intent.REGISTER_PROJECT, f"{register.group(2).strip()}|{register.group(1).strip()}")

    note = re.match(r"^(?:add|save)\s+(?:a\s+)?note\s+(?:for|to)\s+(?:my\s+)?(.+?)\s+project\s*:\s*(.+)$", text, re.IGNORECASE)
    if note:
        return ParsedIntent(Intent.PROJECT_NOTE, f"{note.group(1).strip()}|{note.group(2).strip()}")
    editor = re.match(r"^(?:set|use)\s+(.+?)\s+as\s+(?:the\s+)?editor\s+for\s+(?:my\s+)?(.+?)\s+project$", text, re.IGNORECASE)
    if editor:
        return ParsedIntent(Intent.SET_PROJECT_EDITOR, f"{editor.group(2).strip()}|{editor.group(1).strip()}")
    startup = re.match(r"^set\s+(?:the\s+)?startup\s+command\s+for\s+(?:my\s+)?(.+?)\s+project\s+(?:to|as)\s+(.+)$", text, re.IGNORECASE)
    if startup:
        return ParsedIntent(Intent.SET_PROJECT_STARTUP, f"{startup.group(1).strip()}|{startup.group(2).strip()}")
    url = re.match(r"^set\s+(?:the\s+)?(?:local\s+)?url\s+for\s+(?:my\s+)?(.+?)\s+project\s+(?:to|as)\s+(https?://\S+)$", text, re.IGNORECASE)
    if url:
        return ParsedIntent(Intent.SET_PROJECT_URL, f"{url.group(1).strip()}|{url.group(2).strip()}")
    status = re.match(r"^(?:show|check|give me)\s+(?:the\s+)?(?:status|context)\s+(?:of|for)\s+(?:my\s+)?(.+?)\s+project$", text, re.IGNORECASE)
    if status:
        return ParsedIntent(Intent.PROJECT_STATUS, status.group(1).strip())

    project = re.match(r"^(?:open|continue|launch|find|locate)\s+(?:my\s+)?(?:project\s+)?(.+?)(?:\s+project|\s+folder)?$", text, re.IGNORECASE)
    explicit_project_words = bool(re.search(r"\b(project|folder)\b", lower))
    if project and explicit_project_words:
        return ParsedIntent(Intent.OPEN_PROJECT, project.group(1).strip())
    if lower in {"list projects", "show projects", "my projects", "discover projects", "scan projects"}:
        return ParsedIntent(Intent.LIST_PROJECTS)

    file_words = (
        "file", "folder", "pdf", "document", "docx", "notes", "resume",
        "presentation", "powerpoint", "notebook", "spreadsheet", "image",
        "photo", "download", "report",
    )
    asks_for_file = any(re.search(rf"\b{re.escape(word)}\b", lower) for word in file_words)
    explicit_file_search = lower.startswith(("find file ", "find my file ", "locate file "))
    if explicit_file_search or (lower.startswith(("find ", "locate ", "show me ", "open ")) and asks_for_file):
        return ParsedIntent(Intent.FIND_FILE, text)

    open_match = re.match(r"^(?:please\s+)?(?:open|launch|start)\s+(.+)$", lower)
    if open_match:
        return ParsedIntent(Intent.OPEN_APP, open_match.group(1).strip())

    search_match = re.match(r"^(?:please\s+)?(?:search(?: the web)? for|google)\s+(.+)$", lower)
    if search_match:
        return ParsedIntent(Intent.WEB_SEARCH, search_match.group(1).strip())
    remember_match = re.match(r"^(?:please\s+)?remember(?: that)?\s+(.+)$", text, re.IGNORECASE)
    if remember_match:
        return ParsedIntent(Intent.REMEMBER, remember_match.group(1).strip())
    if lower in {"what do you remember", "show memories", "list memories", "my memories"}:
        return ParsedIntent(Intent.LIST_MEMORY)
    forget_match = re.match(r"^(?:forget|delete memory)\s+(\d+)$", lower)
    if forget_match:
        return ParsedIntent(Intent.FORGET_MEMORY, forget_match.group(1))
    if lower in {"what time is it", "tell me the time", "time", "date"}:
        return ParsedIntent(Intent.TIME)
    if lower in {"system info", "system information", "computer info", "pc info"}:
        return ParsedIntent(Intent.SYSTEM_INFO)
    if lower in {"help", "what can you do", "commands"}:
        return ParsedIntent(Intent.HELP)
    return ParsedIntent(Intent.CHAT, text)
