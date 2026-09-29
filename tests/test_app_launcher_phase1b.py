from pathlib import Path

from app.services.app_launcher import AppCandidate, AppLauncher


def launcher_with(candidates, apps=None):
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.apps = apps or {}
    launcher.discovered = candidates
    return launcher


def test_discovered_application_exact_match_is_ranked_first(tmp_path: Path):
    spotify = AppCandidate("Spotify", str(tmp_path / "Spotify.lnk"), "start_menu")
    helper = AppCandidate("Spotify Helper", str(tmp_path / "helper.exe"), "installation")
    launcher = launcher_with([helper, spotify])

    matches = launcher.find_matches("spotify")

    assert matches[0].name == "Spotify"
    assert matches[0].score == 1.0


def test_user_alias_resolves_to_configured_application():
    launcher = launcher_with([], {"visual studio code": {"aliases": ["code editor"], "commands": ["code"]}})

    match = launcher.find_matches("code editor")[0]

    assert match.source == "alias:visual studio code"
    assert match.target == "code"


def test_launch_uses_argument_list_and_never_shell(monkeypatch, tmp_path: Path):
    executable = tmp_path / "Safe App.exe"
    executable.touch()
    calls = []
    monkeypatch.setattr("app.services.app_launcher.subprocess.Popen", lambda args, shell: calls.append((args, shell)))
    launcher = launcher_with([])

    success, _ = launcher.launch_candidate(AppCandidate("Safe App", str(executable), "installation"))

    assert success is True
    assert calls == [([str(executable)], False)]


def test_stale_discovered_target_explains_failure(tmp_path: Path):
    launcher = launcher_with([])

    success, reply = launcher.launch_candidate(AppCandidate("Missing App", str(tmp_path / "missing.exe"), "registry"))

    assert success is False
    assert "no longer available" in reply
