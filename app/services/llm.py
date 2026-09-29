from __future__ import annotations

from dataclasses import dataclass

from app.config import settings

SYSTEM_INSTRUCTION = f"""
You are {settings.assistant_name}, a practical desktop AI assistant built as a
portfolio project. Give clear, accurate answers. Use saved memories only when
relevant. Never claim a desktop action was completed unless the local command
router reports that it was performed. Do not expose secrets or API keys.
""".strip()


@dataclass
class GeminiStatus:
    configured: bool
    ready: bool
    model: str
    message: str


class GeminiService:
    """Gemini integration with safe diagnostics and graceful local fallback."""

    def __init__(self) -> None:
        self._client = None
        self._initialization_error = ""
        self._last_error = ""
        self._initialize()

    def _initialize(self) -> None:
        if not settings.api_key_configured:
            self._initialization_error = "GEMINI_API_KEY is missing or still contains a placeholder."
            return
        try:
            from google import genai

            # Passing the key explicitly removes ambiguity about which shell or
            # environment variable the SDK is reading.
            self._client = genai.Client(api_key=settings.gemini_api_key)
        except Exception as exc:  # import/configuration failures
            self._initialization_error = f"{type(exc).__name__}: {exc}"
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def status(self) -> GeminiStatus:
        if self.enabled:
            message = "Gemini client initialized. Send a test prompt to verify the key and quota."
            if self._last_error:
                message = f"Client initialized, but the last request failed: {self._last_error}"
            return GeminiStatus(True, True, settings.gemini_model, message)
        return GeminiStatus(
            configured=settings.api_key_configured,
            ready=False,
            model=settings.gemini_model,
            message=self._initialization_error or "Gemini is unavailable.",
        )

    def reply(self, prompt: str, memories: list[str]) -> str:
        if not self.enabled:
            return (
                "Gemini is not connected. Open Settings → AI Diagnostics in this dashboard, "
                "then check that GEMINI_API_KEY is saved in the root .env file and restart Odysseus."
            )

        memory_context = "\n".join(f"- {item}" for item in memories[:10]) or "None"
        full_prompt = (
            f"{SYSTEM_INSTRUCTION}\n\nRelevant saved memories:\n{memory_context}\n\n"
            f"User message: {prompt}"
        )
        try:
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=full_prompt,
            )
            text = getattr(response, "text", None)
            self._last_error = ""
            return text.strip() if text else "Gemini returned an empty response."
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return (
                "Gemini could not answer this request. Local commands still work. "
                f"Open AI Diagnostics for the exact error type ({type(exc).__name__})."
            )

    def connection_test(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, self.status().message
        try:
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents="Reply with exactly: ODYSSEUS_GEMINI_CONNECTED",
            )
            text = (getattr(response, "text", "") or "").strip()
            if "ODYSSEUS_GEMINI_CONNECTED" in text:
                self._last_error = ""
                return True, f"Gemini connection successful using {settings.gemini_model}."
            return False, f"Gemini responded, but the test phrase was unexpected: {text[:120]}"
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False, self._last_error
