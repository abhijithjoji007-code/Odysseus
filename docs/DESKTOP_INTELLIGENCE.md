# Desktop Intelligence Design

## File matching

The file finder deliberately avoids a heavyweight vector database. On an 8 GB laptop, a bounded scan of common folders is simpler and more transparent. Every candidate receives a score based on:

- exact query-token matches in the filename and parent folder
- fuzzy filename similarity
- requested file type
- requested time window
- modification recency

The assistant automatically opens only a high-confidence result. Ambiguous results require a numbered selection.

## Application discovery

Odysseus combines three local discovery sources: per-user and all-user Start Menu shortcuts, executable files in common Windows installation locations, and validated `DisplayIcon` targets from Windows uninstall registry metadata. Results are normalized, deduplicated, and ranked. An ambiguous name produces a numbered, session-safe choice instead of silently opening the wrong program.

User aliases and system fallbacks live in `app/data/apps.json`. Every launch target is validated and passed directly to Windows without `shell=True`. Launch successes and failures are recorded in `app/data/tool_audit.jsonl`.

## Project discovery and aliases

Project discovery performs a bounded scan of `PROJECT_SEARCH_ROOTS`, Desktop, Documents, and `PROJECT_SCAN_PATH`. It recognizes markers for Python, Node.js, Java/Maven, Gradle, Rust, Go, Flutter, PHP, .NET, and Xcode projects. Generated and dependency folders are excluded. Matches are ranked by name and saved aliases; ambiguous results use session-safe numbered selection.

Aliases remain persisted in `app/data/projects.json`. Paths are validated during registration and checked again before opening. A validated project opens in VS Code when its command is available, otherwise in the platform file manager. No project file is executed.

## Tool boundary

Each desktop action is deterministic Python code rather than arbitrary LLM-generated commands. This separation is essential for safety, testing, and truthful portfolio claims.
