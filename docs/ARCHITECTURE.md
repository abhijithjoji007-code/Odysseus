# Odysseus v6 Architecture

```text
Browser UI
   |
FastAPI API
   |
OdysseusAssistant
   |-- Intent Router -> local commands
   |-- Mission Engine -> visible multi-stage workflows
   |-- Project Analyzer -> deterministic read-only repository snapshot
   |-- Gemini Service -> grounded advisory report
   |-- Memory Store -> SQLite
   |-- App Launcher -> ranked Windows discovery + validated launches
   `-- System Tools -> CPU/RAM/disk/battery
```

Project Intelligence deliberately separates **deterministic evidence collection** from **LLM interpretation**. The scanner produces facts. Gemini receives a bounded JSON snapshot and provides recommendations grounded only in that snapshot.
