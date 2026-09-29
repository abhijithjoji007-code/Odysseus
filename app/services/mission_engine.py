from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.schemas import Mission, MissionStep


@dataclass(frozen=True)
class MissionTemplate:
    kind: str
    title: str
    triggers: tuple[str, ...]
    steps: tuple[tuple[str, str, str], ...]


TEMPLATES = (
    MissionTemplate(
        kind="project_intelligence",
        title="Project Intelligence Mission",
        triggers=(
            "analyze my project", "analyse my project", "review my project", "review this repository",
            "explain this project", "scan my codebase", "project intelligence",
        ),
        steps=(
            ("Scanner", "Map the repository", "Read the configured project safely without executing its code."),
            ("Architect", "Explain the architecture", "Identify entry points, modules, dependencies, and data flow."),
            ("Reviewer", "Find engineering risks", "Inspect TODOs, repository hygiene, security signals, and test coverage."),
            ("Advisor", "Prioritize improvements", "Produce a practical, ranked improvement plan grounded in scan evidence."),
            ("Memory", "Archive project baseline", "Save a compact baseline for comparison in later scans."),
        ),
    ),
    MissionTemplate(
        kind="developer_session",
        title="Developer Workspace Mission",
        triggers=("work on my ai project", "start coding", "developer session", "work on odysseus"),
        steps=(
            ("Planner", "Inspect workspace", "Identify the configured project folder and launch plan."),
            ("Automation", "Open development tools", "Open VS Code and the project folder safely."),
            ("System", "Check local environment", "Report CPU, memory, disk, and project readiness."),
            ("Memory", "Load project context", "Recall saved project notes and previous goals."),
        ),
    ),
    MissionTemplate(
        kind="study",
        title="Adaptive Learning Mission",
        triggers=("teach me", "help me learn", "study ", "learn "),
        steps=(
            ("Planner", "Define learning objective", "Convert the topic into a focused learning path."),
            ("Tutor", "Build concept sequence", "Explain concepts from foundations to application."),
            ("Tutor", "Create active recall", "Generate questions and a short self-test."),
            ("Memory", "Save learning summary", "Store the mission outcome for later revision."),
        ),
    ),
    MissionTemplate(
        kind="research",
        title="Biotechnology Research Mission",
        triggers=("research ", "find papers", "biotech research", "latest advances"),
        steps=(
            ("Planner", "Frame the research question", "Define scope, keywords, and expected output."),
            ("Research", "Produce a structured briefing", "Generate a clear, evidence-aware overview using Gemini."),
            ("Reviewer", "Check limitations", "Separate established facts, uncertainty, and suggested verification."),
            ("Memory", "Archive research brief", "Save a compact summary for later use."),
        ),
    ),
    MissionTemplate(
        kind="career",
        title="Career Preparation Mission",
        triggers=("interview", "internship", "resume", "career"),
        steps=(
            ("Planner", "Clarify the target", "Identify role, company, deadline, and current preparation."),
            ("Coach", "Create preparation plan", "Build a practical roadmap and priority list."),
            ("Reviewer", "Generate practice material", "Create interview questions or resume checkpoints."),
            ("Memory", "Save next actions", "Store the most important follow-up actions."),
        ),
    ),
)


class MissionEngine:
    """Turns broad goals into visible, deterministic workflows using safe callbacks."""

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            self.data_path.write_text("[]", encoding="utf-8")

    def detect(self, message: str) -> MissionTemplate | None:
        lowered = message.lower().strip()
        for template in TEMPLATES:
            if any(trigger in lowered for trigger in template.triggers):
                return template
        return None

    def plan(self, message: str, template: MissionTemplate) -> Mission:
        topic = self._extract_topic(message, template.kind)
        mission = Mission(
            id=uuid.uuid4().hex[:10],
            title=template.title,
            objective=message.strip(),
            kind=template.kind,
            steps=[
                MissionStep(id=f"step-{index}", agent=agent, title=title, detail=detail)
                for index, (agent, title, detail) in enumerate(template.steps, start=1)
            ],
        )
        if topic:
            mission.title = f"{template.title}: {topic[:55]}"
        return mission

    def execute(
        self,
        mission: Mission,
        *,
        llm_reply: Callable[[str], str],
        open_vscode: Callable[[], tuple[bool, str]],
        system_summary: Callable[[], str],
        memory_context: Callable[[], list[str]],
        save_memory: Callable[[str], None],
        project_scan: Callable[[], tuple[object, str]] | None = None,
        project_review: Callable[[object], str] | None = None,
    ) -> Mission:
        mission.status = "running"
        total = len(mission.steps)
        outputs: list[str] = []

        for index, step in enumerate(mission.steps, start=1):
            step.status = "running"
            try:
                if mission.kind == "developer_session":
                    result = self._run_developer_step(step.agent, open_vscode, system_summary, memory_context)
                elif mission.kind == "project_intelligence":
                    result = self._run_project_step(step.agent, project_scan, project_review)
                else:
                    result = self._run_reasoning_step(mission, step.agent, llm_reply, memory_context)
                outputs.append(f"### {step.agent}: {step.title}\n{result}")
                step.status = "completed"
            except Exception as exc:
                step.status = "failed"
                outputs.append(f"### {step.agent}: {step.title}\nCould not complete this step: {exc}")
                mission.status = "failed"
                break
            mission.progress = round(index / total * 100)

        mission.output = "\n\n".join(outputs)
        if mission.status != "failed":
            mission.status = "completed"
            mission.progress = 100
            save_memory(f"Mission completed: {mission.title}. Objective: {mission.objective[:300]}")
        self._save(mission)
        return mission

    def list(self, limit: int = 10) -> list[dict]:
        records = self._load()
        return list(reversed(records[-limit:]))

    def _run_developer_step(self, agent: str, open_vscode, system_summary, memory_context) -> str:
        if agent == "Planner":
            return "Workspace plan created: open the approved editor, inspect system readiness, then restore saved context."
        if agent == "Automation":
            success, message = open_vscode()
            return message if success else f"VS Code was not opened: {message}"
        if agent == "System":
            return system_summary()
        memories = memory_context()
        return "Relevant saved context:\n" + ("\n".join(f"- {m}" for m in memories[:5]) if memories else "- No project memories saved yet.")

    def _run_project_step(self, agent: str, project_scan, project_review) -> str:
        if project_scan is None:
            raise RuntimeError("Project Intelligence is not configured.")
        snapshot, summary = project_scan()
        if agent == "Scanner":
            return summary
        if agent == "Architect":
            entrypoints = ", ".join(snapshot.entrypoints[:12]) or "No conventional entry points detected."
            top = ", ".join(snapshot.top_level[:20]) or "No top-level items detected."
            return f"Top-level structure: {top}.\nLikely entry points and manifests: {entrypoints}."
        if agent == "Reviewer":
            if not snapshot.findings and not snapshot.todos:
                return "No obvious repository-hygiene or static review signals were detected by the lightweight scanner."
            findings = [
                f"- [{item.severity.upper()}] {item.title}: {item.detail}"
                + (f" ({item.file}:{item.line})" if item.file else "")
                for item in snapshot.findings[:12]
            ]
            todo_lines = [f"- {item}" for item in snapshot.todos[:8]]
            return (
                "Static findings:\n" + ("\n".join(findings) or "- None")
                + "\nTODO/FIXME sample:\n" + ("\n".join(todo_lines) or "- None")
            )
        if agent == "Advisor":
            if project_review is not None:
                return project_review(snapshot)
            return "Prioritize secrets hygiene, tests, documentation, modular boundaries, and reproducible setup based on the scan."
        return (
            f"Project baseline saved: {snapshot.project_name}; {snapshot.total_files} files; "
            f"{snapshot.total_lines} lines; {len(snapshot.findings)} findings; {len(snapshot.todos)} TODO markers."
        )

    def _run_reasoning_step(self, mission: Mission, agent: str, llm_reply, memory_context) -> str:
        context = "\n".join(memory_context()[:5]) or "No saved context."
        prompt = (
            f"You are the {agent} agent inside Odysseus. Mission type: {mission.kind}. "
            f"Objective: {mission.objective}. Saved context: {context}. "
            "Complete only your assigned stage. Be concrete, student-friendly, and concise. "
            "Do not claim you browsed the web, opened files, or performed actions unless explicitly stated."
        )
        return llm_reply(prompt)

    def _extract_topic(self, message: str, kind: str) -> str:
        cleaned = re.sub(r"\s+", " ", message).strip(" .")
        prefixes = {
            "study": ("teach me", "help me learn", "study", "learn"),
            "research": ("research", "find papers on", "find papers about"),
        }
        for prefix in prefixes.get(kind, ()):
            if cleaned.lower().startswith(prefix):
                return cleaned[len(prefix):].strip(" :")
        return ""

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.data_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, mission: Mission) -> None:
        records = self._load()
        records.append(mission.model_dump())
        self.data_path.write_text(json.dumps(records[-50:], indent=2), encoding="utf-8")
