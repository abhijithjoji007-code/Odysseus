from pathlib import Path

from app.assistant import OdysseusAssistant
from app.services.file_finder import FileMatch


class FakeFinder:
    def __init__(self, matches):
        self.matches = matches
        self.opened = []

    def search(self, _query):
        return self.matches

    def open_path(self, path):
        self.opened.append(path)
        return True, f"Opening {path.name}."


class FakeAudit:
    def record(self, *_args, **_kwargs):
        return None


class MissionGuard:
    def __init__(self):
        self.calls = 0

    def detect(self, _message):
        self.calls += 1
        return None


def make_assistant(matches):
    assistant = OdysseusAssistant()
    assistant.file_finder = FakeFinder(matches)
    assistant.audit = FakeAudit()
    assistant.missions = MissionGuard()
    return assistant


def test_resume_command_bypasses_career_mission(tmp_path: Path):
    resume = tmp_path / "Resume.pdf"
    match = FileMatch(resume, score=0.95, modified=1.0)
    assistant = make_assistant([match])

    response = assistant.handle("Open my latest resume", session_id="browser_a")

    assert response.action == "open_file"
    assert assistant.file_finder.opened == [resume]
    assert assistant.missions.calls == 0


def test_pending_choices_are_session_isolated_and_cancellable(tmp_path: Path):
    first = FileMatch(tmp_path / "Microbiology_A.pdf", score=0.60, modified=2.0)
    second = FileMatch(tmp_path / "Microbiology_B.pdf", score=0.58, modified=1.0)
    assistant = make_assistant([first, second])

    search = assistant.handle("Open my microbiology notes", session_id="browser_a")
    assert search.action == "find_file"

    unrelated = assistant.handle("1", session_id="browser_b")
    assert unrelated.action == "chat"
    assert assistant.file_finder.opened == []

    invalid = assistant.handle("9", session_id="browser_a")
    assert invalid.action == "file_selection"
    assert invalid.success is False

    cancelled = assistant.handle("Cancel", session_id="browser_a")
    assert cancelled.action == "cancel_file_selection"
    assert "browser_a" not in assistant._pending_files


def test_number_opens_displayed_result_after_find_command(tmp_path: Path):
    first = FileMatch(tmp_path / "Microbiology_A.pdf", score=0.60, modified=2.0)
    second = FileMatch(tmp_path / "Microbiology_B.pdf", score=0.58, modified=1.0)
    assistant = make_assistant([first, second])

    search = assistant.handle("Find my microbiology PDF", session_id="browser_a")
    assert search.action == "find_file"
    assert "Reply with the number" in search.reply

    selected = assistant.handle("1", session_id="browser_a")

    assert selected.action == "open_file"
    assert selected.success is True
    assert assistant.file_finder.opened == [first.path]
    assert "browser_a" not in assistant._pending_files
