from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import shlex
import socket
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


EXCLUDED_DIRS = {
    ".git", ".idea", ".mypy_cache", ".pytest_cache", ".venv", "__pycache__",
    "build", "dist", "node_modules", "target", "venv",
}
PROJECT_MARKERS = {
    "package.json": "JavaScript/Node.js",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "build.gradle.kts": "Kotlin/Gradle",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pubspec.yaml": "Flutter/Dart",
    "composer.json": "PHP",
}


@dataclass(frozen=True)
class ProjectCandidate:
    name: str
    path: Path
    project_type: str
    markers: tuple[str, ...]
    score: float = 0.0
    source: str = "discovered"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "project_type": self.project_type,
            "markers": list(self.markers),
            "score": round(self.score, 3),
            "source": self.source,
        }


class ProjectRegistry:
    def __init__(
        self,
        path: Path,
        search_roots: list[Path] | None = None,
        max_directories: int = 6000,
        timeout_seconds: float = 4.0,
    ) -> None:
        self.path = path
        self.search_roots = self._unique_existing(search_roots or [])
        self.max_directories = max(1, max_directories)
        self.timeout_seconds = max(0.05, timeout_seconds)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")
        self._catalog: list[ProjectCandidate] | None = None

    @staticmethod
    def _unique_existing(paths: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()
        for item in paths:
            resolved = item.expanduser().resolve()
            key = os.path.normcase(str(resolved))
            if resolved.is_dir() and key not in seen:
                seen.add(key)
                result.append(resolved)
        return result

    def _load_raw(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _profiles(self) -> dict[str, dict]:
        raw = self._load_raw()
        profiles: dict[str, dict] = {}
        for alias, value in raw.items():
            if isinstance(value, str):
                profiles[str(alias)] = {"path": value, "aliases": [str(alias)], "notes": []}
            elif isinstance(value, dict) and value.get("path"):
                item = dict(value)
                item.setdefault("aliases", [str(alias)])
                item.setdefault("notes", [])
                profiles[str(alias)] = item
        return profiles

    def _save_profiles(self, profiles: dict[str, dict]) -> None:
        self.path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, str]:
        return {alias: str(profile["path"]) for alias, profile in self._profiles().items()}

    def register(self, alias: str, folder: str) -> tuple[bool, str]:
        project_path = Path(folder).expanduser().resolve()
        if not project_path.is_dir():
            return False, f"That project folder does not exist: {project_path}"
        clean_alias = alias.strip().lower()
        data = self._profiles()
        existing = next((dict(v) for v in data.values() if self._same_path(str(v.get("path", "")), project_path)), None)
        profile = existing or {"path": str(project_path), "aliases": [], "notes": []}
        profile["path"] = str(project_path)
        profile["aliases"] = sorted(set([*profile.get("aliases", []), clean_alias]))
        data[clean_alias] = profile
        self._save_profiles(data)
        self._catalog = None
        return True, f"Registered {project_path.name} as '{alias.strip()}'."

    def list(self) -> dict[str, str]:
        return self._load()

    def profile_for(self, candidate: ProjectCandidate) -> dict:
        for profile in self._profiles().values():
            if self._same_path(str(profile.get("path", "")), candidate.path):
                return profile
        return {"path": str(candidate.path), "aliases": [], "notes": []}

    def update_profile(self, query: str, field: str, value: str) -> tuple[bool, str]:
        matches = self.find_matches(query, limit=2)
        if not matches or (len(matches) > 1 and matches[0].score - matches[1].score < 0.12):
            return False, f"I could not uniquely identify the '{query}' project. Use its registered alias."
        candidate = matches[0]
        profiles = self._profiles()
        key = next((k for k, p in profiles.items() if self._same_path(str(p.get("path", "")), candidate.path)), query.strip().lower())
        profile = profiles.get(key, {"path": str(candidate.path), "aliases": [key], "notes": []})
        if field == "notes":
            notes = list(profile.get("notes", []))
            notes.append({"text": value.strip(), "created_at": datetime.now(timezone.utc).isoformat()})
            profile[field] = notes[-10:]
        else:
            profile[field] = value.strip()
        profiles[key] = profile
        self._save_profiles(profiles)
        self._catalog = None
        return True, f"Updated {field.replace('_', ' ')} for {candidate.name}."

    def project_context(self, candidate: ProjectCandidate) -> dict:
        path = candidate.path
        profile = self.profile_for(candidate)
        readme = next((p.name for p in path.iterdir() if p.is_file() and p.name.lower().startswith("readme")), None)
        todo_files = sorted(p.name for p in path.iterdir() if p.is_file() and ("todo" in p.name.lower() or "task" in p.name.lower()))[:5]
        git = self._git_status(path)
        return {
            "name": candidate.name, "path": str(path), "project_type": candidate.project_type,
            "git": git, "readme": readme, "todo_files": todo_files,
            "editor": profile.get("editor", "auto"), "startup_command": profile.get("startup_command"),
            "localhost_url": profile.get("localhost_url"), "notes": profile.get("notes", [])[-5:],
        }

    @staticmethod
    def _git_status(path: Path) -> dict:
        if not (path / ".git").exists() or not shutil.which("git"):
            return {"repository": False}
        try:
            branch = subprocess.run(["git", "-C", str(path), "branch", "--show-current"], capture_output=True, text=True, timeout=2, shell=False)
            status = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True, text=True, timeout=2, shell=False)
            changes = len([line for line in status.stdout.splitlines() if line.strip()])
            return {"repository": True, "branch": branch.stdout.strip() or "detached", "changes": changes, "clean": changes == 0}
        except (OSError, subprocess.SubprocessError):
            return {"repository": True, "error": "Git status unavailable"}

    def refresh_discovery(self) -> list[ProjectCandidate]:
        candidates: dict[str, ProjectCandidate] = {}
        for alias, value in self._load().items():
            project_path = Path(value).expanduser()
            if project_path.is_dir():
                candidate = self._describe(project_path.resolve(), source=f"alias:{alias}")
                candidates[os.path.normcase(str(candidate.path))] = candidate

        started = time.monotonic()
        visited = 0
        stop = False
        for root in self.search_roots:
            for current, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIRS and not d.startswith(".")]
                visited += 1
                if visited > self.max_directories or time.monotonic() - started > self.timeout_seconds:
                    stop = True
                    break
                current_path = Path(current)
                markers = self._markers(files)
                if markers or any(name.endswith((".sln", ".csproj", ".xcodeproj")) for name in files + dirs):
                    candidate = self._describe(current_path, files=files, dirs=dirs)
                    key = os.path.normcase(str(candidate.path))
                    candidates.setdefault(key, candidate)
                    # A recognized project owns its generated subtrees, but nested
                    # source repositories remain discoverable if they have markers.
                    dirs[:] = [d for d in dirs if d.lower() not in {"build", "dist", "target"}]
            if stop:
                break
        self._catalog = sorted(candidates.values(), key=lambda item: item.name.lower())
        return list(self._catalog)

    def catalog(self, refresh: bool = False) -> list[ProjectCandidate]:
        if refresh or self._catalog is None:
            return self.refresh_discovery()
        return list(self._catalog)

    def find_matches(self, query: str, limit: int = 5) -> list[ProjectCandidate]:
        clean = self._clean_query(query)
        aliases = self._load()
        alias_path = aliases.get(clean)
        catalog = self.catalog()
        scored: list[ProjectCandidate] = []
        for item in catalog:
            alias_names = [name for name, value in aliases.items() if self._same_path(value, item.path)]
            name = item.name.lower()
            ratio = SequenceMatcher(None, clean, name).ratio()
            token_score = sum(1 for token in clean.split() if token in name) / max(1, len(clean.split()))
            score = max(ratio * 0.72 + token_score * 0.28, 0.0)
            if clean == name:
                score = 0.98
            if clean in name or name in clean:
                score = max(score, 0.86)
            if clean in alias_names:
                score = 1.0
            if alias_path and self._same_path(alias_path, item.path):
                score = 1.0
            if score >= 0.34:
                scored.append(ProjectCandidate(item.name, item.path, item.project_type, item.markers, score, item.source))
        return sorted(scored, key=lambda item: (-item.score, item.name.lower()))[:limit]

    def open_candidate(self, candidate: ProjectCandidate) -> tuple[bool, str]:
        project_path = candidate.path.resolve()
        if not project_path.is_dir():
            return False, f"The project folder no longer exists: {project_path}"
        profile = self.profile_for(candidate)
        preferred = str(profile.get("editor", "auto")).lower()
        editor_commands = {"vscode": "code", "visual studio code": "code", "pycharm": "pycharm", "cursor": "cursor"}
        configured_editor = editor_commands.get(preferred)
        code = shutil.which(configured_editor) if configured_editor else shutil.which("code")
        try:
            if code:
                subprocess.Popen([code, str(project_path)], shell=False)
                destination = preferred if configured_editor else "Visual Studio Code"
            elif os.name == "nt":
                os.startfile(str(project_path))  # type: ignore[attr-defined]
                destination = "File Explorer"
            else:
                opener = shutil.which("xdg-open") or shutil.which("open")
                if not opener:
                    return False, "No supported editor or folder opener is available."
                subprocess.Popen([opener, str(project_path)], shell=False)
                destination = "the default file manager"
            return True, f"Opening {candidate.name} ({candidate.project_type}) in {destination}."
        except OSError as exc:
            return False, f"Could not open project '{candidate.name}': {exc}"

    def startup_details(self, candidate: ProjectCandidate) -> tuple[str | None, str | None]:
        profile = self.profile_for(candidate)
        return profile.get("startup_command"), profile.get("localhost_url")

    @staticmethod
    def _local_url(url: str) -> tuple[bool, str, int]:
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"} or host not in {"127.0.0.1", "localhost", "::1"}:
                return False, "", 0
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return True, host, port
        except ValueError:
            return False, "", 0

    @staticmethod
    def _port_is_open(host: str, port: int, timeout: float = 0.25) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _url_is_ready(url: str, timeout: float = 0.75) -> bool:
        try:
            request = urllib.request.Request(url, method="GET", headers={"User-Agent": "Odysseus/6"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return 100 <= response.status < 500
        except urllib.error.HTTPError as exc:
            # A 4xx response still proves that the local web server is running.
            # Some frameworks intentionally have no route at "/".
            return 100 <= exc.code < 500
        except Exception:
            return False

    @staticmethod
    def _open_url(url: str) -> bool:
        """Open a URL using the native Windows handler, with a portable fallback."""
        if os.name == "nt":
            try:
                os.startfile(url)  # type: ignore[attr-defined]
                return True
            except OSError:
                pass
        return bool(webbrowser.open_new_tab(url))

    def run_startup(self, candidate: ProjectCandidate, readiness_timeout: float = 20.0) -> tuple[bool, str]:
        command, url = self.startup_details(candidate)
        if not command:
            return False, f"No startup command is configured for {candidate.name}."
        local_target: tuple[str, int] | None = None
        if url:
            valid, host, port = self._local_url(url)
            if not valid:
                return False, "The configured project URL must use http:// or https:// with localhost or 127.0.0.1."
            local_target = (host, port)
            if self._port_is_open(host, port):
                return False, (
                    f"Port {port} is already in use, so {candidate.name} was not started. "
                    "Choose a different port for the project and update its configured URL."
                )
        try:
            args = shlex.split(command, posix=os.name != "nt")
            if not args:
                return False, "The configured startup command is empty."
            process = subprocess.Popen(args, cwd=str(candidate.path), shell=False)
            if not url or not local_target:
                return True, f"Started {candidate.name} with the confirmed command. No local URL is configured."

            deadline = time.monotonic() + max(0.5, readiness_timeout)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return False, (
                        f"{candidate.name} stopped before its website became ready at {url}. "
                        "Check the startup command and its terminal output."
                    )
                if self._url_is_ready(url):
                    if self._open_url(url):
                        return True, f"Started {candidate.name} and opened {url}."
                    return False, f"{candidate.name} is running at {url}, but Windows could not open the browser automatically."
                time.sleep(0.4)
            return False, (
                f"{candidate.name} was started, but {url} did not become ready within {readiness_timeout:g} seconds. "
                "Check the configured URL, port, and startup command."
            )
        except (OSError, ValueError) as exc:
            return False, f"Could not start {candidate.name}: {exc}"

    def open(self, alias: str) -> tuple[bool, str]:
        matches = self.find_matches(alias)
        if not matches:
            return False, f"I could not find a project matching '{alias}'."
        return self.open_candidate(matches[0])

    @staticmethod
    def _same_path(value: str, path: Path) -> bool:
        try:
            return os.path.normcase(str(Path(value).expanduser().resolve())) == os.path.normcase(str(path.resolve()))
        except OSError:
            return False

    @staticmethod
    def _clean_query(query: str) -> str:
        value = query.strip().lower()
        for word in ("open", "find", "locate", "continue", "launch", "my", "the", "project", "folder"):
            value = " ".join(token for token in value.split() if token != word)
        return value.strip()

    @staticmethod
    def _markers(files: list[str]) -> list[str]:
        return sorted(name for name in files if name in PROJECT_MARKERS)

    @classmethod
    def _describe(cls, path: Path, files: list[str] | None = None, dirs: list[str] | None = None, source: str = "discovered") -> ProjectCandidate:
        if files is None or dirs is None:
            try:
                entries = list(path.iterdir())
                files = [entry.name for entry in entries if entry.is_file()]
                dirs = [entry.name for entry in entries if entry.is_dir()]
            except OSError:
                files, dirs = [], []
        markers = cls._markers(files)
        kinds = [PROJECT_MARKERS[name] for name in markers]
        if any(name.endswith((".sln", ".csproj")) for name in files):
            kinds.append(".NET")
        if any(name.endswith(".xcodeproj") for name in dirs):
            kinds.append("Apple/Xcode")
        project_type = " + ".join(dict.fromkeys(kinds)) if kinds else "Project folder"
        return ProjectCandidate(path.name, path, project_type, tuple(markers), source=source)
