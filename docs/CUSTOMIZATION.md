# Customization

## Change name or model

Edit `.env`:

```env
ASSISTANT_NAME=Odysseus
GEMINI_MODEL=gemini-flash-latest
```

## Add an approved application

Run Odysseus once. It creates `app/data/apps.json` from the defaults. Most installed programs are discovered automatically. To add a personal phrase for an app, add it to that app's `aliases` list. You can also add a validated Windows executable path under `commands`. Keep the file valid JSON and never add commands copied from untrusted sources.

Example:

```json
"visual studio code": {
  "aliases": ["code editor", "my editor"],
  "commands": ["code"]
}
```

## Add a mission type

Open `app/services/mission_engine.py` and add a `MissionTemplate` to `TEMPLATES` with:

- a stable `kind`
- a display title
- clear trigger phrases
- agent, title, and detail tuples

Then extend `_run_reasoning_step()` or add a safe dedicated executor when the mission needs a real local action.

## Change the theme

Edit the CSS variables at the top of `app/static/styles.css`.

## Analyze another project

Set an absolute path in `.env` and restart:

```env
PROJECT_SCAN_PATH=C:\Users\YourName\Documents\YourProject
```
