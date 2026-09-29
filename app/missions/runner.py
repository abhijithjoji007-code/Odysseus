from __future__ import annotations

import threading, time
from datetime import datetime, timezone
from typing import Any
from app.missions.models import MissionRecord, MissionStep, now_iso
from app.missions.planner import MissionPlanner
from app.missions.store import MissionStore

class MissionRunner:
    def __init__(self, store: MissionStore, registry) -> None:
        self.store, self.registry, self.planner = store, registry, MissionPlanner()
        self._live: dict[str, MissionRecord] = {}
        self._lock = threading.RLock()

    def start(self, objective: str, session_id: str) -> MissionRecord | None:
        mission = self.planner.plan(objective, session_id)
        if not mission: return None
        with self._lock: self._live[mission.id] = mission
        self.store.save(mission)
        threading.Thread(target=self._run, args=(mission,), daemon=True).start()
        return mission

    def get(self, mission_id: str, session_id: str | None = None) -> MissionRecord | None:
        mission = self._live.get(mission_id) or self.store.get(mission_id)
        if mission and mission.status in {"waiting_input", "waiting_permission"}:
            try: age = (datetime.now(timezone.utc) - datetime.fromisoformat(mission.updated_at)).total_seconds()
            except ValueError: age = 0
            if age > 600:
                mission.status, mission.prompt = "failed", "This mission request expired. Start the mission again."
                step = next((s for s in mission.steps if s.status in {"waiting_input", "waiting_permission"}), None)
                if step: step.status, step.error = "failed", "Pending request expired."
                self._finish(mission)
        return mission if mission and (session_id is None or mission.session_id == session_id) else None

    def list(self, limit=20): return self.store.list(limit)

    def respond(self, mission_id: str, session_id: str, response: str) -> MissionRecord | None:
        mission = self.get(mission_id, session_id)
        if not mission or mission.status in {"completed", "failed", "cancelled"}: return None
        clean = response.strip().lower()
        if clean in {"cancel", "no", "stop"}:
            mission.status = "cancelled"
            for s in mission.steps:
                if s.status in {"pending", "waiting_input", "waiting_permission"}: s.status = "cancelled"
            mission.prompt, mission.choices = "", []; self._persist(mission); return mission
        step = next((s for s in mission.steps if s.status in {"waiting_input", "waiting_permission"}), None)
        if not step: return mission
        if step.status == "waiting_input":
            if not response.strip().isdigit() or not 1 <= int(response) <= len(mission.choices): return mission
            selected = mission.choices[int(response)-1]
            step.arguments = selected; step.status = "pending"
            if step.depends_on:
                source_step = next((s for s in mission.steps if s.id == step.depends_on[-1]), None)
                if source_step and "matches" in source_step.output: source_step.output["matches"] = [selected]
        else:
            if clean not in {"confirm", "yes", "run it"}: return mission
            step.arguments["_confirmed"] = True; step.status = "pending"
        mission.status, mission.prompt, mission.choices = "running", "", []
        self._persist(mission); threading.Thread(target=self._run, args=(mission,), daemon=True).start(); return mission

    def cancel(self, mission_id, session_id): return self.respond(mission_id, session_id, "cancel")

    def _persist(self, m):
        done = sum(s.status in {"completed", "failed", "skipped", "cancelled"} for s in m.steps)
        m.progress = round(done / len(m.steps) * 100) if m.steps else 100
        self.store.save(m)

    def _run(self, mission: MissionRecord) -> None:
        try:
            self._run_steps(mission)
        except Exception as exc:
            # A background-thread exception must always become visible mission
            # state; otherwise the dashboard waits forever with no explanation.
            step = next((s for s in mission.steps if s.status == "running"), None)
            if step:
                step.status = "failed"
                step.error = f"Unexpected mission error: {type(exc).__name__}: {exc}"
            mission.status = "failed"
            self._finish(mission)

    def _run_steps(self, mission: MissionRecord) -> None:
        mission.status = "running"; self._persist(mission)
        for step in mission.steps:
            if mission.status == "cancelled": self._finish(mission); return
            if step.status == "completed": continue
            if any(next(x for x in mission.steps if x.id == dep).status != "completed" for dep in step.depends_on):
                step.status = "skipped"; step.error = "A required earlier step did not complete."; continue
            args = self._arguments(mission, step)
            if args is None: return
            step.status, step.started_at, step.attempts = "running", now_iso(), step.attempts + 1; self._persist(mission)
            confirmed = bool(args.pop("_confirmed", False))
            result = self.registry.execute(step.tool, args, mission.session_id, confirmed=confirmed)
            if mission.status == "cancelled": step.status = "cancelled"; self._finish(mission); return
            if result.confirmation_required:
                step.status, mission.status = "waiting_permission", "waiting_permission"
                mission.prompt = f"{result.message} Reply Confirm or Cancel."; self._persist(mission); return
            if not result.success and step.attempts == 1 and step.tool in {"search_files", "discover_apps", "discover_projects", "read_document"}:
                time.sleep(.05); step.attempts += 1; result = self.registry.execute(step.tool, args, mission.session_id)
            if not result.success:
                step.status, step.error, mission.status = "failed", result.message, "failed"; self._finish(mission); return
            step.status, step.output, step.completed_at = "completed", {"message": result.message, **result.data}, now_iso(); self._persist(mission)
        mission.status = "completed"; self._finish(mission)

    def _arguments(self, mission: MissionRecord, step: MissionStep) -> dict[str, Any] | None:
        args = dict(step.arguments)
        previous = [s for s in mission.steps if s.id in step.depends_on]
        source = previous[-1].output if previous else {}
        matches = source.get("matches", [])
        if step.tool in {"read_document", "project_status", "open_project", "open_application"} and not args:
            if len(matches) > 1:
                mission.status, step.status, mission.choices = "waiting_input", "waiting_input", matches[:5]
                mission.prompt = "Choose one result:\n" + "\n".join(f"{i}. {x.get('name') or x.get('path')}" for i,x in enumerate(mission.choices,1)) + "\nReply with a number or Cancel."
                self._persist(mission); return None
            if not matches:
                step.status, step.error, mission.status = "failed", "No matching item was available.", "failed"; self._finish(mission); return None
            args = matches[0]
        if step.tool == "read_document": args = {"path": args.get("path")}
        if step.tool == "generate_study_material": args = {"text": source.get("text", ""), "objective": mission.objective}
        if step.tool == "record_project_session":
            project_step = next(s for s in mission.steps if s.tool == "discover_projects")
            selected = project_step.output.get("matches", [{}])[0]
            args = {"project": selected.get("name", mission.objective), "report": "Project opened and status inspected through Mission Engine."}
        return args

    def _finish(self, mission):
        completed = [s.title for s in mission.steps if s.status == "completed"]
        failed = [f"{s.title}: {s.error}" for s in mission.steps if s.status == "failed"]
        material = next((s.output.get("material") for s in mission.steps if s.output.get("material")), "")
        mission.final_report = material or ("Completed: " + ", ".join(completed) + (("\nFailed: " + "; ".join(failed)) if failed else ""))
        self._persist(mission)
