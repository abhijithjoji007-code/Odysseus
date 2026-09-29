from app.assistant import OdysseusAssistant
from app.services.app_launcher import AppCandidate


class FakeLauncher:
    def __init__(self, matches):
        self.matches = matches
        self.opened = []

    def find_matches(self, _query):
        return self.matches

    def refresh_discovery(self):
        return len(self.matches)

    def launch_candidate(self, candidate):
        self.opened.append(candidate)
        return True, f"Opening {candidate.name}."


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, *args):
        self.entries.append(args)


def make_assistant(matches):
    assistant = OdysseusAssistant()
    assistant.launcher = FakeLauncher(matches)
    assistant.audit = FakeAudit()
    return assistant


def test_exact_application_match_launches_and_records_history():
    spotify = AppCandidate("Spotify", "Spotify.lnk", "start_menu", 1.0)
    assistant = make_assistant([spotify])

    response = assistant.handle("Open Spotify", session_id="browser_a")

    assert response.action == "open_app"
    assert assistant.launcher.opened == [spotify]
    assert assistant.audit.entries[0][0] == "open_application"


def test_ambiguous_application_choice_is_session_safe():
    code = AppCandidate("Visual Studio Code", "code.exe", "installation", 0.84)
    codium = AppCandidate("VSCodium", "codium.exe", "installation", 0.84)
    assistant = make_assistant([code, codium])

    search = assistant.handle("Open VS", session_id="browser_a")
    assert search.action == "app_selection"

    unrelated = assistant.handle("1", session_id="browser_b")
    assert unrelated.action == "chat"
    assert assistant.launcher.opened == []

    selected = assistant.handle("2", session_id="browser_a")
    assert selected.action == "open_app"
    assert assistant.launcher.opened == [codium]


def test_unknown_application_has_clear_failure():
    assistant = make_assistant([])

    response = assistant.handle("Start Definitely Missing App", session_id="browser_a")

    assert response.success is False
    assert "could not find" in response.reply.lower()
