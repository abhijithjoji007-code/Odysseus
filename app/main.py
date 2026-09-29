from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.assistant import OdysseusAssistant
from app.config import ASSISTANT_NAME, STATIC_DIR, settings
from app.schemas import AssistantRequest, AssistantResponse
from app.services.system_tools import system_metrics
from app.tools.health import tool_health
from pydantic import BaseModel, Field

app = FastAPI(
    title=f"{ASSISTANT_NAME} Mission AI Assistant",
    version="6.0.0",
    description="A local-first mission-based AI assistant with Gemini, memory, voice, and safe desktop actions.",
)
assistant = OdysseusAssistant()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
def health() -> dict[str, object]:
    ai = assistant.llm.status()
    return {
        "status": "ok",
        "version": "6.0.0",
        "assistant": ASSISTANT_NAME,
        "ai": {"configured": ai.configured, "ready": ai.ready, "model": ai.model, "message": ai.message},
        "environment": {"env_file_found": settings.env_path.exists(), "env_file_name": settings.env_path.name},
        "capabilities": ["secure_tool_registry", "persistent_mission_engine", "live_mission_progress", "document_study_workflow", "intelligent_file_search", "file_opening", "start_menu_app_discovery", "project_registry", "tool_audit", "project_intelligence", "voice", "memory", "system_metrics", "gemini"],
    }


@app.get("/api/tools/health")
def tools_health() -> dict[str, object]:
    return tool_health(assistant.tools)


@app.post("/api/ai/test")
def test_ai() -> dict[str, object]:
    success, message = assistant.llm.connection_test()
    return {"success": success, "message": message, "model": settings.gemini_model}


@app.get("/api/system")
def system() -> dict[str, int | float | str]:
    return system_metrics()


@app.get("/api/memories")
def memories() -> list[dict[str, int | str]]:
    return [{"id": item.id, "content": item.content} for item in assistant.memory.list(limit=20)]


@app.get("/api/missions")
def missions() -> list[dict]:
    return assistant.mission_runner.list(limit=20)

class MissionReply(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    response: str = Field(min_length=1, max_length=1000)

@app.get("/api/missions/{mission_id}")
def mission_status(mission_id: str, session_id: str) -> dict:
    mission = assistant.mission_runner.get(mission_id, session_id)
    if not mission: return {"error": "Mission not found for this session."}
    return mission.model_dump()

@app.post("/api/missions/{mission_id}/respond")
def mission_respond(mission_id: str, request: MissionReply) -> dict:
    mission = assistant.mission_runner.respond(mission_id, request.session_id, request.response)
    return mission.model_dump() if mission else {"error": "Mission is not waiting for this session."}


@app.get("/api/apps")
def apps() -> dict[str, object]:
    return {"count": len(assistant.launcher.available_apps()), "apps": assistant.launcher.available_apps()}


@app.get("/api/projects")
def projects() -> dict[str, str]:
    return assistant.projects.list()


@app.get("/api/project/scan")
def project_scan() -> dict:
    snapshot, summary = assistant._scan_project()
    return {"summary": summary, "snapshot": snapshot.to_dict()}


@app.post("/api/assistant", response_model=AssistantResponse)
def run_assistant(request: AssistantRequest) -> AssistantResponse:
    return assistant.handle(request.message, session_id=request.session_id)
