from pathlib import Path

from app.services.mission_engine import MissionEngine


def test_detects_study_mission(tmp_path: Path):
    engine = MissionEngine(tmp_path / "missions.json")
    template = engine.detect("Teach me PCR from the basics")
    assert template is not None
    assert template.kind == "study"


def test_executes_study_mission(tmp_path: Path):
    engine = MissionEngine(tmp_path / "missions.json")
    template = engine.detect("Teach me PCR")
    mission = engine.plan("Teach me PCR", template)
    saved = []
    completed = engine.execute(
        mission,
        llm_reply=lambda prompt: "Agent output",
        open_vscode=lambda: (True, "Opened VS Code"),
        system_summary=lambda: "System ready",
        memory_context=lambda: [],
        save_memory=saved.append,
    )
    assert completed.status == "completed"
    assert completed.progress == 100
    assert all(step.status == "completed" for step in completed.steps)
    assert saved


def test_developer_mission_calls_safe_launcher(tmp_path: Path):
    engine = MissionEngine(tmp_path / "missions.json")
    template = engine.detect("I am going to work on my AI project")
    mission = engine.plan("I am going to work on my AI project", template)
    calls = []
    completed = engine.execute(
        mission,
        llm_reply=lambda prompt: "unused",
        open_vscode=lambda: (calls.append("vscode") or True, "Opened VS Code"),
        system_summary=lambda: "System ready",
        memory_context=lambda: ["Continue mission engine"],
        save_memory=lambda content: None,
    )
    assert completed.status == "completed"
    assert calls == ["vscode"]
