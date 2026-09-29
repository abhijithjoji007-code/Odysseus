from pathlib import Path
import urllib.error

from app.services.project_registry import ProjectRegistry
from app.services.project_registry import ProjectCandidate


def test_register_and_list_project(tmp_path: Path):
    project = tmp_path / "demo"
    project.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json")
    success, _ = registry.register("main", str(project))
    assert success
    assert registry.list()["main"] == str(project.resolve())


def test_discovers_and_identifies_project_types(tmp_path: Path):
    python_project = tmp_path / "biotech-ai"
    python_project.mkdir()
    (python_project / "pyproject.toml").write_text("[project]\nname='demo'", encoding="utf-8")
    web_project = tmp_path / "biotech-dashboard"
    web_project.mkdir()
    (web_project / "package.json").write_text("{}", encoding="utf-8")

    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    catalog = registry.refresh_discovery()

    assert {item.name for item in catalog} == {"biotech-ai", "biotech-dashboard"}
    assert next(item for item in catalog if item.name == "biotech-ai").project_type == "Python"
    assert next(item for item in catalog if item.name == "biotech-dashboard").project_type == "JavaScript/Node.js"


def test_alias_is_ranked_first(tmp_path: Path):
    project = tmp_path / "Odysseus_AI_Assistant_v6"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    assert registry.register("assistant", str(project))[0]

    matches = registry.find_matches("assistant")

    assert matches[0].path == project.resolve()
    assert matches[0].score == 1.0


def test_discovery_excludes_generated_directories(tmp_path: Path):
    generated = tmp_path / "node_modules" / "fake-package"
    generated.mkdir(parents=True)
    (generated / "package.json").write_text("{}", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])

    assert registry.refresh_discovery() == []


def test_discovery_honors_directory_limit(tmp_path: Path):
    for index in range(5):
        folder = tmp_path / f"folder-{index}"
        folder.mkdir()
        (folder / "package.json").write_text("{}", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path], max_directories=2)

    assert len(registry.refresh_discovery()) <= 1


def test_project_profile_keeps_editor_url_command_and_notes(tmp_path: Path):
    project = tmp_path / "biotech-hub"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    assert registry.register("biotech", str(project))[0]

    assert registry.update_profile("biotech", "editor", "Visual Studio Code")[0]
    assert registry.update_profile("biotech", "startup_command", "python app.py")[0]
    assert registry.update_profile("biotech", "localhost_url", "http://127.0.0.1:8000")[0]
    assert registry.update_profile("biotech", "notes", "Finish quiz endpoint")[0]

    match = registry.find_matches("biotech")[0]
    context = registry.project_context(match)
    assert context["editor"] == "Visual Studio Code"
    assert context["startup_command"] == "python app.py"
    assert context["localhost_url"] == "http://127.0.0.1:8000"
    assert context["notes"][-1]["text"] == "Finish quiz endpoint"


def test_project_context_detects_readme_todo_and_git_absence(tmp_path: Path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]", encoding="utf-8")
    (project / "README.md").write_text("demo", encoding="utf-8")
    (project / "TODO.md").write_text("next", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    candidate = registry.refresh_discovery()[0]

    context = registry.project_context(candidate)

    assert context["readme"] == "README.md"
    assert context["todo_files"] == ["TODO.md"]
    assert context["git"] == {"repository": False}


def test_confirmed_startup_waits_and_opens_configured_url(tmp_path: Path, monkeypatch):
    project = tmp_path / "web-app"
    project.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    assert registry.register("web", str(project))[0]
    assert registry.update_profile("web", "startup_command", "python app.py")[0]
    assert registry.update_profile("web", "localhost_url", "http://127.0.0.1:8501")[0]
    candidate = registry.find_matches("web")[0]

    class Process:
        def poll(self):
            return None

    opened = []
    monkeypatch.setattr("app.services.project_registry.subprocess.Popen", lambda *a, **k: Process())
    monkeypatch.setattr(registry, "_port_is_open", lambda *a, **k: False)
    monkeypatch.setattr(registry, "_url_is_ready", lambda *a, **k: True)
    monkeypatch.setattr(registry, "_open_url", lambda url: opened.append(url) or True)

    success, message = registry.run_startup(candidate, readiness_timeout=1)

    assert success is True
    assert opened == ["http://127.0.0.1:8501"]
    assert "opened" in message


def test_http_404_still_counts_as_ready(monkeypatch):
    class NotFound(urllib.error.HTTPError):
        pass

    def raise_404(*_args, **_kwargs):
        raise NotFound("http://127.0.0.1:8501", 404, "Not Found", {}, None)

    monkeypatch.setattr("app.services.project_registry.urllib.request.urlopen", raise_404)

    assert ProjectRegistry._url_is_ready("http://127.0.0.1:8501") is True


def test_startup_does_not_run_when_configured_port_is_occupied(tmp_path: Path, monkeypatch):
    project = tmp_path / "web-app"
    project.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    candidate = ProjectCandidate("web-app", project, "Python", ())
    monkeypatch.setattr(registry, "startup_details", lambda _candidate: ("python app.py", "http://localhost:8000"))
    monkeypatch.setattr(registry, "_port_is_open", lambda *a, **k: True)
    launched = []
    monkeypatch.setattr("app.services.project_registry.subprocess.Popen", lambda *a, **k: launched.append(True))

    success, message = registry.run_startup(candidate)

    assert success is False
    assert launched == []
    assert "already in use" in message


def test_startup_reports_early_process_exit(tmp_path: Path, monkeypatch):
    project = tmp_path / "web-app"
    project.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    candidate = ProjectCandidate("web-app", project, "Python", ())
    monkeypatch.setattr(registry, "startup_details", lambda _candidate: ("python app.py", "http://localhost:8501"))
    monkeypatch.setattr(registry, "_port_is_open", lambda *a, **k: False)

    class Process:
        def poll(self):
            return 1

    monkeypatch.setattr("app.services.project_registry.subprocess.Popen", lambda *a, **k: Process())

    success, message = registry.run_startup(candidate, readiness_timeout=1)

    assert success is False
    assert "stopped before" in message


def test_startup_without_url_still_succeeds(tmp_path: Path, monkeypatch):
    project = tmp_path / "script"
    project.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json", [tmp_path])
    candidate = ProjectCandidate("script", project, "Python", ())
    monkeypatch.setattr(registry, "startup_details", lambda _candidate: ("python worker.py", None))
    monkeypatch.setattr("app.services.project_registry.subprocess.Popen", lambda *a, **k: object())

    success, message = registry.run_startup(candidate)

    assert success is True
    assert "No local URL" in message
