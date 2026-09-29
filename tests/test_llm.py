from app.services.llm import GeminiService


def test_status_never_contains_api_key():
    service = GeminiService()
    status = service.status()
    rendered = f"{status.configured} {status.ready} {status.model} {status.message}"
    assert "GEMINI_API_KEY=" not in rendered


def test_connection_test_fails_cleanly_when_disabled():
    service = GeminiService()
    if not service.enabled:
        success, message = service.connection_test()
        assert success is False
        assert isinstance(message, str)
        assert message
