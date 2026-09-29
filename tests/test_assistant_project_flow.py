from pathlib import Path

from app.assistant import OdysseusAssistant
from app.services.project_registry import ProjectCandidate


class FakeProjects:
    def __init__(self, matches):
        self.matches = matches
        self.opened = []
        self.started = []

    def find_matches(self, _query):
        return self.matches

    def refresh_discovery(self):
        return self.matches

    def open_candidate(self, candidate):
        self.opened.append(candidate)
        return True, f"Opening {candidate.name}."

    def project_context(self, candidate):
        return {"git": {"repository": True, "branch": "main", "changes": 2}, "readme": "README.md", "todo_files": ["TODO.md"], "notes": [{"text": "Finish tests"}]}

    def startup_details(self, _candidate):
        return "python app.py", "http://127.0.0.1:8000"

    def run_startup(self, candidate):
        self.started.append(candidate)
        return True, f"Started {candidate.name}."


class FakeAudit:
    def record(self, *_args, **_kwargs):
        return None


def make_assistant(matches):
    assistant = OdysseusAssistant()
    assistant.projects = FakeProjects(matches)
    assistant.audit = FakeAudit()
    return assistant


def candidate(path: Path, score: float) -> ProjectCandidate:
    return ProjectCandidate(path.name, path, "Python", ("pyproject.toml",), score)


def test_confident_project_opens_directly(tmp_path: Path):
    project = candidate(tmp_path / "odysseus", 0.98)
    assistant = make_assistant([project])

    response = assistant.handle("Open my odysseus project", session_id="browser_a")

    assert response.action == "open_project"
    assert assistant.projects.opened == [project]


def test_ambiguous_project_selection_is_session_safe(tmp_path: Path):
    first = candidate(tmp_path / "biotech-ai", 0.80)
    second = candidate(tmp_path / "biotech-hub", 0.79)
    assistant = make_assistant([first, second])

    search = assistant.handle("Find my biotech project", session_id="browser_a")
    assert search.action == "project_selection"

    unrelated = assistant.handle("1", session_id="browser_b")
    assert unrelated.action == "chat"
    assert assistant.projects.opened == []

    invalid = assistant.handle("8", session_id="browser_a")
    assert invalid.action == "project_selection"
    assert invalid.success is False

    selected = assistant.handle("2", session_id="browser_a")
    assert selected.action == "open_project"
    assert assistant.projects.opened == [second]


def test_project_selection_can_be_cancelled(tmp_path: Path):
    assistant = make_assistant([
        candidate(tmp_path / "college-one", 0.75),
        candidate(tmp_path / "college-two", 0.74),
    ])
    assistant.handle("Open my college folder", session_id="browser_a")

    response = assistant.handle("Cancel", session_id="browser_a")

    assert response.action == "cancel_project_selection"
    assert "browser_a" not in assistant._pending_projects


def test_missing_project_has_clear_configuration_hint():
    assistant = make_assistant([])

    response = assistant.handle("Open my missing project", session_id="browser_a")

    assert response.success is False
    assert "PROJECT_SEARCH_ROOTS" in response.reply


def test_continue_requires_confirmation_before_startup(tmp_path: Path):
    project = candidate(tmp_path / "biotech", 0.98)
    assistant = make_assistant([project])

    continued = assistant.handle("Continue my biotech project", session_id="browser_a")

    assert continued.action == "open_project"
    assert assistant.projects.started == []
    assert "Reply Confirm" in continued.reply

    confirmed = assistant.handle("Confirm", session_id="browser_a")

    assert confirmed.action == "project_startup"
    assert assistant.projects.started == [project]


def test_continue_startup_can_be_cancelled(tmp_path: Path):
    project = candidate(tmp_path / "biotech", 0.98)
    assistant = make_assistant([project])
    assistant.handle("Continue my biotech project", session_id="browser_a")

    cancelled = assistant.handle("Cancel", session_id="browser_a")

    assert cancelled.action == "cancel_project_startup"
    assert assistant.projects.started == []
