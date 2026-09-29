from __future__ import annotations

import re, uuid
from app.missions.models import MissionRecord, MissionStep

class MissionPlanner:
    def plan(self, objective: str, session_id: str) -> MissionRecord | None:
        text, low = objective.strip(), objective.lower()
        if "summar" in low and ("question" in low or "revision" in low):
            query = re.split(r",| and summar", text, maxsplit=1)[0]
            query = re.sub(r"^(open|find)\s+(my\s+)?", "", query, flags=re.I).strip()
            return self._make(session_id, text, "study_document", "Study Document Mission", [
                ("Find document", "search_files", {"query": query}, []),
                ("Read selected document", "read_document", {}, ["step-1"]),
                ("Create summary and revision questions", "generate_study_material", {}, ["step-2"]),
            ])
        if "project" in low and "status" in low and ("open" in low or "continue" in low):
            query = re.sub(r"\b(continue|open|my|project|show|its|status|and|in|vs code|vscode)\b", " ", text, flags=re.I)
            query = re.sub(r"\s+", " ", query).strip() or "Odysseus"
            return self._make(session_id, text, "project_session", "Project Session Mission", [
                ("Resolve project", "discover_projects", {"query": query}, []),
                ("Inspect project status", "project_status", {}, ["step-1"]),
                ("Open project", "open_project", {}, ["step-1"]),
                ("Record project session", "record_project_session", {}, ["step-2", "step-3"]),
            ])
        if re.search(r"\b(open|launch|start)\b", low) and " and " in low and any(x in low for x in ("spotify", "calculator", "notepad", "chrome", "code")):
            phrase = re.split(r",?\s*then\s+show|,?\s*then\s+report", text, flags=re.I)[0]
            phrase = re.sub(r"^(open|launch|start)\s+", "", phrase, flags=re.I)
            names = [re.sub(r"^(open|launch|start)\s+", "", x.strip(), flags=re.I) for x in re.split(r"\s+and\s+|,", phrase) if x.strip()]
            steps = []
            for name in names[:5]:
                n = len(steps)+1; steps += [(f"Find {name}", "discover_apps", {"query": name}, []), (f"Launch {name}", "open_application", {}, [f"step-{n}"])]
            return self._make(session_id, text, "desktop_setup", "Desktop Setup Mission", steps)
        return None

    def _make(self, session, objective, workflow, title, specs):
        return MissionRecord(id=uuid.uuid4().hex[:12], session_id=session, objective=objective, workflow=workflow, title=title,
            steps=[MissionStep(id=f"step-{i}", title=s[0], tool=s[1], arguments=s[2], depends_on=s[3]) for i,s in enumerate(specs,1)])
