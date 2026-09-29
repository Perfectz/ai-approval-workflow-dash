# Director Studio workspace

This repository contains a local film-production dashboard and a reusable agent workflow. It also retains the standalone scratch-audio tool and its technical demo.

## Work on a film

Read `.agents/skills/director-studio/SKILL.md` and use the shared CLI/MCP tools in `docs/AGENT_INTERFACE.md`. Query project state before producing a deliverable. Use exact artifact versions, source pins and task leases. The dashboard is where the director reviews prompts and outputs together. Never record an approval merely because a tool ran successfully. The imported audio lab is a sandbox, not an approved creative project.

## Work on the application

Application maintenance does not need film-stage approval. Preserve user data in `studio-data/` and existing media in `outputs/`. Use temporary data directories for automated/browser tests; do not test approval by changing the user's real film records. No paid generation or cloud upload is part of ordinary app validation.

- Shared business rules: `studio/store.py`; agent surface: `studio/agent_tools.py`.
- HTTP/UI: `studio/app.py`, `src/main.tsx`, `src/styles.css`.
- Workflow contract: `workflows/comic-to-wan-v1.json`, `docs/WORKFLOW_SPEC.md`.
- Start: `START_STUDIO.ps1`; app at `http://127.0.0.1:8767`.
- Build: `npm run build`.
- Relevant tests: `.venv/Scripts/python.exe -m unittest discover -s tests -v`.

Keep the CLI, MCP and dashboard on the same rules. Do not add agent approval operations or hidden paid retries. Model changes require checking current provider documentation. Describe local previews and verified provider executions separately.
