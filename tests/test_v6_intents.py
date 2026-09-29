from app.services.intent_router import Intent, parse_intent


def test_file_intent():
    assert parse_intent("Open my latest microbiology PDF").intent == Intent.FIND_FILE


def test_open_project_intent():
    parsed = parse_intent("Continue my biotech project")
    assert parsed.intent == Intent.OPEN_PROJECT
    assert parsed.argument == "biotech"


def test_find_project_and_folder_intents():
    assert parse_intent("Find my Odysseus project").intent == Intent.OPEN_PROJECT
    assert parse_intent("Open project biotech hub").argument == "biotech hub"
    assert parse_intent("Open my college folder").intent == Intent.OPEN_PROJECT


def test_discover_projects_intent():
    assert parse_intent("Discover projects").intent == Intent.LIST_PROJECTS


def test_register_project_intent():
    parsed = parse_intent(r"Register C:\\Work\\AI as my biotech project")
    assert parsed.intent == Intent.REGISTER_PROJECT
