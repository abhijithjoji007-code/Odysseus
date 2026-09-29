from pathlib import Path
from app.missions.planner import MissionPlanner
from app.missions.store import MissionStore

def test_history_persists_across_store_instances(tmp_path: Path):
    path = tmp_path / "missions.json"
    mission = MissionPlanner().plan("Open Spotify and Calculator, then show me what was launched", "browser_a")
    MissionStore(path).save(mission)
    loaded = MissionStore(path).get(mission.id)
    assert loaded and loaded.session_id == "browser_a" and loaded.workflow == "desktop_setup"
