from __future__ import annotations

import json
import threading
from pathlib import Path
from app.missions.models import MissionRecord, now_iso

class MissionStore:
    def __init__(self, path: Path, limit: int = 100) -> None:
        self.path, self.limit, self.lock = path, limit, threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError): return []

    def save(self, mission: MissionRecord) -> None:
        with self.lock:
            mission.updated_at = now_iso()
            rows = [x for x in self._load() if x.get("id") != mission.id]
            rows.append(mission.model_dump())
            self.path.write_text(json.dumps(rows[-self.limit:], indent=2), encoding="utf-8")

    def get(self, mission_id: str) -> MissionRecord | None:
        with self.lock:
            row = next((x for x in self._load() if x.get("id") == mission_id), None)
            return MissionRecord.model_validate(row) if row else None

    def list(self, limit: int = 20) -> list[dict]:
        with self.lock: return list(reversed(self._load()[-limit:]))
