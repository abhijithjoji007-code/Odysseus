from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", "dist", "build",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".next", "coverage",
}
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".json", ".md",
    ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".env.example", ".bat", ".ps1",
}
LANGUAGE_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript/React",
    ".jsx": "JavaScript/React", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".md": "Markdown", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
}
ENTRYPOINT_NAMES = {
    "main.py", "app.py", "server.py", "manage.py", "index.js", "index.ts", "main.ts", "main.js",
    "package.json", "pyproject.toml", "requirements.txt", "dockerfile", "run.bat", "readme.md",
}


@dataclass
class Finding:
    severity: str
    title: str
    detail: str
    file: str = ""
    line: int | None = None


@dataclass
class ProjectSnapshot:
    root: str
    project_name: str
    total_files: int
    text_files: int
    total_lines: int
    languages: dict[str, int]
    top_level: list[str]
    entrypoints: list[str]
    dependencies: list[str]
    todos: list[str]
    findings: list[Finding] = field(default_factory=list)
    git: dict[str, str | int | bool] = field(default_factory=dict)
    tree: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    def compact_for_llm(self) -> str:
        payload = self.to_dict()
        payload["tree"] = payload["tree"][:120]
        payload["todos"] = payload["todos"][:30]
        payload["dependencies"] = payload["dependencies"][:80]
        return json.dumps(payload, indent=2, ensure_ascii=False)


class ProjectAnalyzer:
    """Read-only repository inspection for Odysseus Project Intelligence.

    The analyzer never executes project code. Git commands are limited to read-only metadata.
    Large/generated folders and binary files are skipped to keep scans fast on modest laptops.
    """

    def __init__(self, root: Path, max_files: int = 1500, max_file_bytes: int = 500_000) -> None:
        self.root = root.resolve()
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def scan(self) -> ProjectSnapshot:
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError(f"Project path does not exist or is not a folder: {self.root}")

        files = list(self._iter_files())
        language_counts: Counter[str] = Counter()
        total_lines = 0
        text_files = 0
        todos: list[str] = []
        entrypoints: list[str] = []
        dependencies: list[str] = []
        findings: list[Finding] = []
        tree: list[str] = []

        for path in files:
            rel = path.relative_to(self.root).as_posix()
            tree.append(rel)
            if path.name.lower() in ENTRYPOINT_NAMES:
                entrypoints.append(rel)
            if self._looks_sensitive(path):
                findings.append(Finding("high", "Potential secret file", "Do not commit credentials or private keys.", rel))
            if not self._is_text(path):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text_files += 1
            lines = text.splitlines()
            total_lines += len(lines)
            language_counts[LANGUAGE_MAP.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "Other")] += 1
            for line_no, line in enumerate(lines, start=1):
                lowered = line.lower()
                if "todo" in lowered or "fixme" in lowered:
                    todos.append(f"{rel}:{line_no} — {line.strip()[:160]}")
                if len(todos) >= 100:
                    break
            findings.extend(self._inspect_text(rel, lines))
            if path.name.lower() in {"requirements.txt", "pyproject.toml", "package.json"}:
                dependencies.extend(self._extract_dependencies(path.name.lower(), text))

        top_level = sorted(p.name for p in self.root.iterdir() if p.name not in EXCLUDED_DIRS)[:80]
        if not (self.root / ".gitignore").exists():
            findings.append(Finding("medium", "Missing .gitignore", "Add a .gitignore before publishing the repository."))
        if not any(name.lower().startswith("readme") for name in top_level):
            findings.append(Finding("medium", "Missing README", "Add setup, architecture, screenshots, and demo instructions."))
        if not any("test" in p.lower() for p in tree):
            findings.append(Finding("medium", "No tests detected", "Add automated tests for core behavior and failure paths."))

        return ProjectSnapshot(
            root=str(self.root),
            project_name=self.root.name,
            total_files=len(files),
            text_files=text_files,
            total_lines=total_lines,
            languages=dict(language_counts.most_common()),
            top_level=top_level,
            entrypoints=sorted(set(entrypoints)),
            dependencies=sorted(set(dependencies)),
            todos=todos[:100],
            findings=self._dedupe_findings(findings)[:80],
            git=self._git_info(),
            tree=tree[:400],
        )

    def _iter_files(self) -> Iterable[Path]:
        count = 0
        for path in self.root.rglob("*"):
            if any(part in EXCLUDED_DIRS for part in path.relative_to(self.root).parts):
                continue
            if not path.is_file():
                continue
            yield path
            count += 1
            if count >= self.max_files:
                break

    @staticmethod
    def _is_text(path: Path) -> bool:
        return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in {
            "dockerfile", "makefile", ".gitignore", ".env.example",
        }

    @staticmethod
    def _looks_sensitive(path: Path) -> bool:
        name = path.name.lower()
        return name in {".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json"} or name.endswith((".pem", ".key", ".p12"))

    @staticmethod
    def _inspect_text(rel: str, lines: list[str]) -> list[Finding]:
        findings: list[Finding] = []
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            lowered = stripped.lower()
            if "shell=true" in lowered:
                findings.append(Finding("high", "Unsafe shell execution", "Avoid shell=True with untrusted input.", rel, line_no))
            if "allow_origins=[\"*\"]" in lowered or "allow_origins=['*']" in lowered:
                findings.append(Finding("medium", "Permissive CORS", "Restrict CORS origins before public deployment.", rel, line_no))
            if "except exception" in lowered and "pass" in lowered:
                findings.append(Finding("low", "Silenced exception", "Log or handle broad exceptions explicitly.", rel, line_no))
            if "debug=true" in lowered:
                findings.append(Finding("medium", "Debug mode enabled", "Disable debug mode in production.", rel, line_no))
        return findings

    @staticmethod
    def _extract_dependencies(filename: str, text: str) -> list[str]:
        if filename == "requirements.txt":
            return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if filename == "package.json":
            try:
                data = json.loads(text)
                result: list[str] = []
                for group in ("dependencies", "devDependencies"):
                    for name, version in data.get(group, {}).items():
                        result.append(f"{name}{version}")
                return result
            except json.JSONDecodeError:
                return []
        if filename == "pyproject.toml":
            return [line.strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")][:100]
        return []

    def _git_info(self) -> dict[str, str | int | bool]:
        if not (self.root / ".git").exists():
            return {"is_repository": False}
        result: dict[str, str | int | bool] = {"is_repository": True}
        commands = {
            "branch": ["git", "branch", "--show-current"],
            "last_commit": ["git", "log", "-1", "--pretty=%h %s"],
            "status": ["git", "status", "--porcelain"],
        }
        for key, command in commands.items():
            try:
                completed = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=3, check=False)
                output = completed.stdout.strip()
                result[key] = len(output.splitlines()) if key == "status" else output
            except (OSError, subprocess.SubprocessError):
                result[key] = "unavailable"
        return result

    @staticmethod
    def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
        seen: set[tuple] = set()
        result: list[Finding] = []
        rank = {"high": 0, "medium": 1, "low": 2}
        for finding in sorted(findings, key=lambda item: rank.get(item.severity, 3)):
            key = (finding.title, finding.file, finding.line)
            if key not in seen:
                result.append(finding)
                seen.add(key)
        return result


def deterministic_summary(snapshot: ProjectSnapshot) -> str:
    languages = ", ".join(f"{name}: {count} files" for name, count in list(snapshot.languages.items())[:6]) or "No recognized source files"
    git = "Git repository detected" if snapshot.git.get("is_repository") else "Git repository not detected"
    high = sum(1 for finding in snapshot.findings if finding.severity == "high")
    medium = sum(1 for finding in snapshot.findings if finding.severity == "medium")
    return (
        f"Scanned {snapshot.total_files} files ({snapshot.text_files} readable text files) and approximately "
        f"{snapshot.total_lines} lines. Languages: {languages}. {git}. "
        f"Detected {len(snapshot.todos)} TODO/FIXME markers and {high} high / {medium} medium review findings."
    )
