import time
from pathlib import Path
from app.missions.runner import MissionRunner
from app.missions.store import MissionStore
from app.tools.models import ToolResult

class FakeRegistry:
    def execute(self, name, args, session_id, confirmed=False):
        if name == "discover_apps":
            return ToolResult(success=True, message="found", data={"matches":[{"name": args["query"], "target": args["query"]+".exe", "source":"test", "score":1.0}]})
        if name == "open_application": return ToolResult(success=True, message=f"Opened {args['name']}", data={"app":args})
        return ToolResult(success=False, message="unexpected")

def wait_terminal(runner, mission_id):
    for _ in range(100):
        mission = runner.get(mission_id)
        if mission.status in {"completed","failed","cancelled"}: return mission
        time.sleep(.01)
    raise AssertionError("mission did not finish")

def test_desktop_workflow_runs_real_registry_steps_and_reports(tmp_path: Path):
    runner = MissionRunner(MissionStore(tmp_path/"m.json"), FakeRegistry())
    mission = runner.start("Open Spotify and Calculator, then show me what was launched", "a")
    done = wait_terminal(runner, mission.id)
    assert done.status == "completed" and done.progress == 100
    assert all(step.status == "completed" for step in done.steps)
    assert "Launch Spotify" in done.final_report

def test_mission_is_bound_to_originating_session(tmp_path: Path):
    runner = MissionRunner(MissionStore(tmp_path/"m.json"), FakeRegistry())
    mission = runner.start("Open Spotify and Calculator, then show me what was launched", "browser_a")
    assert runner.get(mission.id, "browser_b") is None


def test_background_exception_becomes_visible_failure(tmp_path: Path):
    class BrokenRegistry:
        def execute(self, *args, **kwargs):
            raise RuntimeError("deliberate test failure")

    runner = MissionRunner(MissionStore(tmp_path / "m.json"), BrokenRegistry())
    mission = runner.planner.plan(
        "Open Spotify and Calculator, then show me what was launched", "session-a"
    )
    assert mission is not None
    runner._live[mission.id] = mission
    runner._run(mission)
    assert mission.status == "failed"
    assert any("RuntimeError" in step.error for step in mission.steps)
