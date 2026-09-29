from app.services.intent_router import Intent, parse_intent


def test_phase1d_project_workflow_intents():
    assert parse_intent("Show status for my biotech project").intent == Intent.PROJECT_STATUS
    assert parse_intent("Add note for my biotech project: finish API").argument == "biotech|finish API"
    assert parse_intent("Set Visual Studio Code as editor for my biotech project").intent == Intent.SET_PROJECT_EDITOR
    assert parse_intent("Set startup command for my biotech project to python app.py").intent == Intent.SET_PROJECT_STARTUP
    assert parse_intent("Set URL for my biotech project to http://127.0.0.1:8000").intent == Intent.SET_PROJECT_URL


def test_open_app_intent() -> None:
    parsed = parse_intent("Open calculator")
    assert parsed.intent == Intent.OPEN_APP
    assert parsed.argument == "calculator"


def test_search_intent() -> None:
    parsed = parse_intent("search for protein folding")
    assert parsed.intent == Intent.WEB_SEARCH
    assert parsed.argument == "protein folding"


def test_memory_intent_preserves_text() -> None:
    parsed = parse_intent("Remember that My Project Uses FastAPI")
    assert parsed.intent == Intent.REMEMBER
    assert parsed.argument == "My Project Uses FastAPI"


def test_chat_fallback() -> None:
    parsed = parse_intent("Explain PCR simply")
    assert parsed.intent == Intent.CHAT


def test_show_me_explanation_is_not_file_search() -> None:
    assert parse_intent("Show me how PCR works").intent == Intent.CHAT


def test_find_papers_remains_available_to_research_mission() -> None:
    assert parse_intent("Find papers on CRISPR delivery").intent == Intent.CHAT


def test_file_phrases_are_detected() -> None:
    assert parse_intent("Find my microbiology PDF").intent == Intent.FIND_FILE
    assert parse_intent("Open my microbiology notes").intent == Intent.FIND_FILE
