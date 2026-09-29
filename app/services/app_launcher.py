from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.config import APPS_CONFIG_PATH


DEFAULT_APPS: dict[str, dict[str, Any]] = {
    "notepad": {"aliases": ["text editor"], "commands": ["notepad.exe"]},
    "calculator": {"aliases": ["calc"], "commands": ["calc.exe"]},
    "paint": {"aliases": ["mspaint"], "commands": ["mspaint.exe"]},
    "file explorer": {"aliases": ["explorer", "files"], "commands": ["explorer.exe"]},
    "settings": {"aliases": ["windows settings"], "commands": ["start", "ms-settings:"]},
    "terminal": {"aliases": ["command prompt", "cmd"], "commands": ["cmd.exe"]},
    "powershell": {"aliases": [], "commands": ["powershell.exe"]},
    "vscode": {"aliases": ["vs code", "visual studio code"], "commands": ["code"]},
}

IGNORED_EXECUTABLES = {
    "uninstall", "unins000", "update", "updater", "setup", "install", "installer",
    "crashpad_handler", "notification_helper", "elevate", "service",
}
COMMON_APP_DIRS = (
    "PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA",
)
REGISTRY_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)


def _normalise(value: str) -> str:
    value = re.sub(r"\.(?:exe|lnk)$", "", value.strip().lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


@dataclass(frozen=True)
class AppCandidate:
    name: str
    target: str
    source: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "source": self.source, "score": round(self.score, 3)}


class AppLauncher:
    """Discover and launch validated Windows application targets without a shell."""

    def __init__(self) -> None:
        self.apps = self._load_apps()
        self.discovered: list[AppCandidate] = []
        self.refresh_discovery()

    def _load_apps(self) -> dict[str, dict[str, Any]]:
        if not APPS_CONFIG_PATH.exists():
            APPS_CONFIG_PATH.write_text(json.dumps(DEFAULT_APPS, indent=2), encoding="utf-8")
            return DEFAULT_APPS.copy()
        try:
            custom = json.loads(APPS_CONFIG_PATH.read_text(encoding="utf-8"))
            return custom if isinstance(custom, dict) else DEFAULT_APPS.copy()
        except (json.JSONDecodeError, OSError):
            return DEFAULT_APPS.copy()

    @staticmethod
    def _start_menu_candidates() -> Iterable[AppCandidate]:
        roots = (
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        )
        for root in roots:
            if root.is_dir():
                for shortcut in root.rglob("*.lnk"):
                    yield AppCandidate(shortcut.stem, str(shortcut), "start_menu")

    @staticmethod
    def _common_location_candidates(max_files: int = 4000) -> Iterable[AppCandidate]:
        scanned = 0
        for variable in COMMON_APP_DIRS:
            root = Path(os.environ.get(variable, ""))
            if not root.is_dir():
                continue
            # Installed programs are normally at most three levels below these roots.
            for executable in root.glob("*/*/*.exe"):
                scanned += 1
                if scanned > max_files:
                    return
                if _normalise(executable.stem) not in IGNORED_EXECUTABLES:
                    yield AppCandidate(executable.stem, str(executable), "installation")
            for executable in root.glob("*/*.exe"):
                scanned += 1
                if scanned > max_files:
                    return
                if _normalise(executable.stem) not in IGNORED_EXECUTABLES:
                    yield AppCandidate(executable.stem, str(executable), "installation")

    @staticmethod
    def _registry_candidates() -> Iterable[AppCandidate]:
        if os.name != "nt":
            return
        try:
            import winreg
        except ImportError:
            return
        hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        for hive in hives:
            for key_path in REGISTRY_UNINSTALL_KEYS:
                try:
                    root = winreg.OpenKey(hive, key_path)
                except OSError:
                    continue
                with root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            child = winreg.OpenKey(root, winreg.EnumKey(root, index))
                            with child:
                                name = str(winreg.QueryValueEx(child, "DisplayName")[0]).strip()
                                icon = str(winreg.QueryValueEx(child, "DisplayIcon")[0]).strip()
                        except OSError:
                            continue
                        # DisplayIcon can include an icon index: app.exe,0.
                        target = icon.strip('"').rsplit(",", 1)[0].strip('"')
                        if name and Path(os.path.expandvars(target)).is_file():
                            yield AppCandidate(name, os.path.expandvars(target), "registry")

    def refresh_discovery(self) -> int:
        if os.name != "nt":
            self.discovered = []
            return 0
        unique: dict[tuple[str, str], AppCandidate] = {}
        for item in (*self._start_menu_candidates(), *self._registry_candidates(), *self._common_location_candidates()):
            key = (_normalise(item.name), os.path.normcase(item.target))
            if key[0] and key not in unique:
                unique[key] = item
        self.discovered = list(unique.values())
        return len(self.discovered)

    def available_apps(self) -> list[str]:
        return sorted(set(self.apps) | {_normalise(item.name) for item in self.discovered})

    def _configured_candidates(self) -> Iterable[AppCandidate]:
        for name, info in self.apps.items():
            aliases = [str(alias) for alias in info.get("aliases", [])]
            commands = [str(command) for command in info.get("commands", [])]
            if commands[:1] == ["start"]:
                commands = commands[1:]
            for command in commands:
                yield AppCandidate(name, str(command), "configured")
            for alias in aliases:
                for command in commands:
                    yield AppCandidate(alias, str(command), f"alias:{name}")

    def find_matches(self, spoken_name: str, limit: int = 5) -> list[AppCandidate]:
        query = _normalise(spoken_name)
        if not query:
            return []
        ranked: list[AppCandidate] = []
        seen_names: set[str] = set()
        for item in (*self._configured_candidates(), *self.discovered):
            name = _normalise(item.name)
            if name == query:
                score = 1.0
            elif name.startswith(query) or query.startswith(name):
                score = 0.84
            elif query in name:
                score = 0.76
            elif set(query.split()) and set(query.split()).issubset(set(name.split())):
                score = 0.70
            else:
                continue
            if name in seen_names:
                continue
            seen_names.add(name)
            ranked.append(AppCandidate(item.name, item.target, item.source, score))
        ranked.sort(key=lambda item: (-item.score, 0 if item.source.startswith("alias:") else 1, len(item.name)))
        return ranked[:limit]

    @staticmethod
    def _resolve_command(command: str) -> str | None:
        expanded = os.path.expandvars(command).replace("/", os.sep)
        if command == "start":
            return command
        if Path(expanded).is_file():
            return expanded
        return shutil.which(expanded)

    def launch_candidate(self, candidate: AppCandidate) -> tuple[bool, str]:
        try:
            if candidate.source == "start_menu":
                os.startfile(candidate.target)  # type: ignore[attr-defined]
            elif candidate.target == "ms-settings:":
                os.startfile(candidate.target)  # type: ignore[attr-defined]
            else:
                resolved = self._resolve_command(candidate.target)
                if not resolved:
                    return False, f"I found {candidate.name}, but its executable is no longer available. Refresh discovery or update its alias."
                subprocess.Popen([resolved], shell=False)
            return True, f"Opening {candidate.name}."
        except (OSError, ValueError) as exc:
            return False, f"I found {candidate.name}, but Windows could not launch it: {exc}"

    def launch(self, spoken_name: str) -> tuple[bool, str]:
        matches = self.find_matches(spoken_name)
        if not matches:
            self.refresh_discovery()
            matches = self.find_matches(spoken_name)
        if not matches:
            return False, f"I could not find an installed application matching '{spoken_name}'."
        return self.launch_candidate(matches[0])
