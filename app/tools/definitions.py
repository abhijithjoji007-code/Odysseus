from __future__ import annotations

from pathlib import Path

from app.services.app_launcher import AppCandidate, AppLauncher
from app.services.file_finder import FileFinder
from app.services.project_registry import ProjectCandidate, ProjectRegistry
from app.services.tool_audit import ToolAudit
from app.tools.models import AppArgs, PathArgs, PermissionLevel, ProjectArgs, QueryArgs, RegisterProjectArgs, ToolResult, UpdateProjectArgs, StudyMaterialArgs, ProjectSessionArgs
from app.tools.registry import SecureToolRegistry, ToolDefinition


def _result(value: tuple[bool, str], **data) -> ToolResult:
    return ToolResult(success=value[0], message=value[1], data=data)


def build_tool_registry(files: FileFinder, apps: AppLauncher, projects: ProjectRegistry, audit: ToolAudit, document_reader=None, llm=None) -> SecureToolRegistry:
    registry = SecureToolRegistry(audit)
    registry.register(ToolDefinition("search_files", "Search configured local roots", QueryArgs, PermissionLevel.READ_ONLY,
        lambda a: ToolResult(success=bool(m := files.search(a.query)), message=f"Found {len(m)} matching files." if m else "No matching files were found.", data={"matches": [x.to_dict() for x in m]}), 8))
    registry.register(ToolDefinition("open_file", "Open one validated local file", PathArgs, PermissionLevel.LOCAL_ACTION,
        lambda a: _result(files.open_path(Path(a.path)), path=a.path)))
    registry.register(ToolDefinition("discover_apps", "Find installed applications", QueryArgs, PermissionLevel.READ_ONLY,
        lambda a: ToolResult(success=bool(m := apps.find_matches(a.query)), message=f"Found {len(m)} matching applications." if m else "No matching applications were found.", data={"matches": [{**x.to_dict(), "target": x.target} for x in m]}), 8))
    registry.register(ToolDefinition("open_application", "Launch one discovered application", AppArgs, PermissionLevel.LOCAL_ACTION,
        lambda a: _result(apps.launch_candidate(AppCandidate(a.name, a.target, a.source, a.score)), app=a.model_dump())))
    registry.register(ToolDefinition("discover_projects", "Find local code projects", QueryArgs, PermissionLevel.READ_ONLY,
        lambda a: ToolResult(success=bool(m := (projects.find_matches(a.query) if a.query != "*" else projects.refresh_discovery())), message=f"Found {len(m)} projects." if m else "No projects were found.", data={"matches": [x.to_dict() for x in m]}), 10))
    registry.register(ToolDefinition("open_project", "Open one discovered project", ProjectArgs, PermissionLevel.LOCAL_ACTION,
        lambda a: _result(projects.open_candidate(ProjectCandidate(a.name, Path(a.path), a.project_type, tuple(a.markers), a.score, a.source)), project=a.model_dump())))
    registry.register(ToolDefinition("project_status", "Read project context", ProjectArgs, PermissionLevel.READ_ONLY,
        lambda a: ToolResult(success=True, message="Project context loaded.", data={"context": projects.project_context(ProjectCandidate(a.name, Path(a.path), a.project_type, tuple(a.markers), a.score, a.source))}), 5))
    registry.register(ToolDefinition("register_project", "Register a project alias", RegisterProjectArgs, PermissionLevel.LOCAL_ACTION,
        lambda a: _result(projects.register(a.alias, a.folder))))
    registry.register(ToolDefinition("update_project", "Update an approved project profile field", UpdateProjectArgs, PermissionLevel.LOCAL_ACTION,
        lambda a: _result(projects.update_profile(a.query, a.field, a.value))))
    registry.register(ToolDefinition("run_project_startup", "Run a stored startup command", ProjectArgs, PermissionLevel.CONFIRMATION_REQUIRED,
        lambda a: _result(projects.run_startup(ProjectCandidate(a.name, Path(a.path), a.project_type, tuple(a.markers), a.score, a.source)), project=a.model_dump()), 30))
    if document_reader is not None:
        registry.register(ToolDefinition("read_document", "Extract bounded text from a supported local document", PathArgs, PermissionLevel.READ_ONLY,
            lambda a: (lambda v: ToolResult(success=v[0], message=v[1], data=v[2]))(document_reader.read(a.path)), 12))
    if llm is not None:
        def study(a):
            if not llm.enabled: return ToolResult(success=False, message="Gemini is unavailable, so study material was not generated.")
            prompt = f"Using only the document text below, identify the latest substantial section, summarize it clearly, and create five revision questions. Objective: {a.objective}\n\nDOCUMENT:\n{a.text}"
            value = llm.reply(prompt, [])
            failed = value.startswith("Gemini could not") or value.startswith("Gemini is not")
            return ToolResult(success=not failed, message="Study material generated." if not failed else value, data={"material": value} if not failed else {})
        registry.register(ToolDefinition("generate_study_material", "Generate grounded study material with Gemini", StudyMaterialArgs, PermissionLevel.READ_ONLY, study, 45))
    def record(a):
        matches = projects.find_matches(a.project)
        return _result(projects.update_profile(a.project, "notes", a.report)) if matches else ToolResult(success=False, message="Project session could not be recorded because the project was not found.")
    registry.register(ToolDefinition("record_project_session", "Store a bounded project-session report", ProjectSessionArgs, PermissionLevel.LOCAL_ACTION, record, 5))
    return registry
