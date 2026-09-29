from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
ENV_PATH = PROJECT_DIR / ".env"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# override=True is intentional: values saved in this project's .env should be
# used instead of stale values inherited from a previous terminal session.
load_dotenv(dotenv_path=ENV_PATH, override=True)


@dataclass(frozen=True)
class Settings:
    assistant_name: str
    gemini_api_key: str
    gemini_model: str
    database_path: Path
    apps_config_path: Path
    env_path: Path
    project_scan_path: Path
    file_search_roots: list[Path]
    project_search_roots: list[Path]

    @property
    def api_key_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.lower() not in {"xxxx", "your_key_here"})


def _clean(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip().strip('"').strip("'")


settings = Settings(
    assistant_name=_clean("ASSISTANT_NAME", "Odysseus") or "Odysseus",
    gemini_api_key=_clean("GEMINI_API_KEY"),
    # The alias tracks Google's currently supported Flash model. It can be
    # replaced in .env without changing Python code.
    gemini_model=_clean("GEMINI_MODEL", "gemini-flash-latest") or "gemini-flash-latest",
    database_path=DATA_DIR / "odysseus.db",
    apps_config_path=DATA_DIR / "apps.json",
    env_path=ENV_PATH,
    project_scan_path=Path(_clean("PROJECT_SCAN_PATH", str(PROJECT_DIR))).expanduser().resolve(),
    file_search_roots=[Path(p.strip()).expanduser().resolve() for p in _clean("FILE_SEARCH_ROOTS", "").split(";") if p.strip()],
    project_search_roots=[Path(p.strip()).expanduser().resolve() for p in _clean("PROJECT_SEARCH_ROOTS", "").split(";") if p.strip()],
)

ASSISTANT_NAME = settings.assistant_name
GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model
DATABASE_PATH = settings.database_path
APPS_CONFIG_PATH = settings.apps_config_path

PROJECT_SCAN_PATH = settings.project_scan_path

FILE_SEARCH_ROOTS = settings.file_search_roots
PROJECT_SEARCH_ROOTS = settings.project_search_roots
