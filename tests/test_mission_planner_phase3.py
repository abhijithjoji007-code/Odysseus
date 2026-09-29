from app.missions.planner import MissionPlanner

def test_plans_three_approved_workflows():
    planner = MissionPlanner()
    study = planner.plan("Open my biochemistry notes, summarize the latest chapter, and create five revision questions", "s1")
    project = planner.plan("Continue my Odysseus project, show its status, and open it in VS Code", "s1")
    desktop = planner.plan("Open Spotify and Calculator, then show me what was launched", "s1")
    assert study.workflow == "study_document" and len(study.steps) == 3
    assert project.workflow == "project_session" and len(project.steps) == 4
    assert desktop.workflow == "desktop_setup" and len(desktop.steps) == 4

def test_single_legacy_project_command_is_not_hijacked():
    assert MissionPlanner().plan("Continue my biotech project", "s1") is None
