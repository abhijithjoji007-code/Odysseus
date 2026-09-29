from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path


@dataclass(frozen=True)
class FileMatch:
    path: Path
    score: float
    modified: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.path.name,
            "path": str(self.path),
            "score": round(self.score, 3),
            "modified": datetime.fromtimestamp(self.modified).isoformat(timespec="seconds"),
        }


class FileFinder:
    @staticmethod
    def match_from_dict(data: dict):
        raw = data.get("modified", 0)
        modified = datetime.fromisoformat(raw).timestamp() if isinstance(raw, str) else float(raw)
        return FileMatch(path=Path(data["path"]), score=float(data.get("score", 0)), modified=modified)
    """Searches common user folders without building a heavy permanent index."""

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".txt", ".md", ".csv", ".xlsx", ".pptx",
        ".py", ".ipynb", ".js", ".ts", ".html", ".css", ".json", ".png", ".jpg", ".jpeg"
    }
    IGNORED_DIRS = {
        ".git", ".venv", "venv", "node_modules", "__pycache__", "appdata",
        ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages",
    }

    def __init__(
        self,
        extra_roots: list[Path] | None = None,
        *,
        max_scanned_files: int = 50_000,
        timeout_seconds: float = 4.0,
    ) -> None:
        home = Path.home()
        roots = [home / "Desktop", home / "Documents", home / "Downloads"]
        if extra_roots:
            roots.extend(extra_roots)
        self.roots = list(dict.fromkeys(root.resolve() for root in roots if root.exists()))
        self.max_scanned_files = max(1, max_scanned_files)
        self.timeout_seconds = max(0.05, timeout_seconds)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        stop = {"open", "find", "show", "me", "my", "the", "file", "document", "latest", "recent"}
        return [token for token in cleaned.split() if token not in stop]

    def search(self, query: str, limit: int = 8) -> list[FileMatch]:
        tokens = self._tokens(query)
        lower = query.lower()
        extension_filter = self._extension_filter(lower)
        recency_days = self._recency_days(lower)
        now = datetime.now().timestamp()
        matches: list[FileMatch] = []
        scanned_files = 0
        deadline = time.monotonic() + self.timeout_seconds

        for root in self.roots:
            for directory, subdirs, files in os.walk(root):
                if time.monotonic() >= deadline or scanned_files >= self.max_scanned_files:
                    break
                subdirs[:] = [d for d in subdirs if d.lower() not in self.IGNORED_DIRS and not d.startswith(".")]
                for filename in files:
                    scanned_files += 1
                    if scanned_files > self.max_scanned_files or time.monotonic() >= deadline:
                        break
                    path = Path(directory) / filename
                    suffix = path.suffix.lower()
                    if suffix not in self.SUPPORTED_EXTENSIONS:
                        continue
                    if extension_filter and suffix not in extension_filter:
                        continue
                    try:
                        modified = path.stat().st_mtime
                    except OSError:
                        continue
                    if recency_days and modified < (datetime.now() - timedelta(days=recency_days)).timestamp():
                        continue
                    searchable = f"{path.stem} {path.parent.name}".lower()
                    token_score = sum(1 for token in tokens if token in searchable) / max(len(tokens), 1)
                    fuzzy = SequenceMatcher(None, " ".join(tokens), path.stem.lower()).ratio() if tokens else 0.0
                    age_days = max((now - modified) / 86400, 0)
                    recency = 1 / (1 + age_days / 30)
                    score = token_score * 0.65 + fuzzy * 0.25 + recency * 0.10
                    if not tokens or score >= 0.16:
                        matches.append(FileMatch(path=path, score=score, modified=modified))
            if time.monotonic() >= deadline or scanned_files >= self.max_scanned_files:
                break

        matches.sort(key=lambda item: (item.score, item.modified), reverse=True)
        return matches[:limit]

    @staticmethod
    def _extension_filter(text: str) -> set[str]:
        mapping = {
            "pdf": {".pdf"}, "resume": {".pdf", ".docx", ".doc"},
            "presentation": {".pptx"}, "powerpoint": {".pptx"},
            "spreadsheet": {".xlsx", ".csv"}, "image": {".png", ".jpg", ".jpeg"},
            "python": {".py", ".ipynb"}, "notebook": {".ipynb"},
        }
        result: set[str] = set()
        for word, extensions in mapping.items():
            if word in text:
                result.update(extensions)
        return result

    @staticmethod
    def _recency_days(text: str) -> int | None:
        if "today" in text:
            return 1
        if "yesterday" in text:
            return 2
        if "last week" in text or "this week" in text:
            return 7
        if "latest" in text or "recent" in text:
            return 90
        return None

    @staticmethod
    def open_path(path: Path) -> tuple[bool, str]:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
            return True, f"Opening {path.name}."
        except OSError as exc:
            return False, f"I found {path.name}, but the operating system could not open it: {exc}"
