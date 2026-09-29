# Project Intelligence

Project Intelligence is the flagship capability introduced in Odysseus v5. It inspects a configured repository without executing the repository's code.

## What it reads

- Folder and file structure
- Recognized source-file counts and approximate lines of code
- Common entry points and dependency manifests
- TODO and FIXME markers
- Lightweight security and repository-hygiene signals
- Read-only Git metadata when the folder contains `.git`

## What it does not do

- It does not run project code.
- It does not install project dependencies.
- It does not execute AI-generated shell commands.
- It does not upload the full repository to Gemini. Gemini receives a bounded structured snapshot containing metadata and selected findings.

## Configure the project folder

Edit `.env`:

```env
PROJECT_SCAN_PATH=C:\Users\YourName\Documents\YourProject
```

For Odysseus to analyze itself, use:

```env
PROJECT_SCAN_PATH=.
```

Restart the server after changing `.env`.

## Start the mission

Use one of these commands:

- `Analyze my project and give me a portfolio readiness report`
- `Review this repository`
- `Explain this project architecture`
- `Scan my codebase`

## Mission stages

1. **Scanner:** Builds the repository snapshot.
2. **Architect:** Identifies structure and likely entry points.
3. **Reviewer:** Surfaces deterministic findings and TODO markers.
4. **Advisor:** Uses Gemini to create a grounded improvement plan.
5. **Memory:** Stores a compact baseline for later comparison.
