from pathlib import Path

from app.services.project_intelligence import ProjectAnalyzer, deterministic_summary
from app.services.mission_engine import MissionEngine


def test_project_scan_collects_structure(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("# TODO: improve\nprint('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi==1.0\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")

    snapshot = ProjectAnalyzer(tmp_path).scan()
    assert snapshot.total_files == 4
    assert snapshot.total_lines >= 4
    assert "app/main.py" in snapshot.entrypoints
    assert snapshot.todos
    assert "fastapi==1.0" in snapshot.dependencies
    assert "Scanned 4 files" in deterministic_summary(snapshot)


def test_project_scan_flags_env(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET=x", encoding="utf-8")
    snapshot = ProjectAnalyzer(tmp_path).scan()
    assert any(item.title == "Potential secret file" for item in snapshot.findings)


def test_project_intelligence_mission_detected(tmp_path: Path):
    engine = MissionEngine(tmp_path / "missions.json")
    template = engine.detect("Analyze my project and review the architecture")
    assert template is not None
    assert template.kind == "project_intelligence"
