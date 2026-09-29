# Director Studio — agent interface

Any agent with local shell access can use the CLI. MCP clients can use the same typed tools. Both enforce the same gates and use the same SQLite project records as the dashboard.

## CLI

Run from this repository:

```powershell
.venv\Scripts\python.exe -m studio.cli list_projects
.venv\Scripts\python.exe -m studio.cli get_workflow
.venv\Scripts\python.exe -m studio.cli get_next_action --json-file request.json
```

Example `request.json`:

```json
{"project_id":"project_REPLACE","scene_id":null}
```

Use a real ID from `list_projects`. Prefer JSON files to nested shell quoting. Results are JSON on stdout; failures are JSON on stderr with exit code 1. Do not commit request files containing lease tokens.

## MCP configuration

Configure this stdio server in the agent client of your choice. This is a configuration example; it has not changed your global client settings.

```json
{
  "mcpServers": {
    "director-studio": {
      "command": "C:\\projects\\ai-approval-workflow-dash\\.venv\\Scripts\\python.exe",
      "args": ["-m", "studio.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\projects\\ai-approval-workflow-dash",
        "DIRECTOR_DATA": "C:\\projects\\ai-approval-workflow-dash\\studio-data"
      }
    }
  }
}
```

For another machine, change the paths. A compatible Python environment must contain `requirements-lock.txt` dependencies. No API key is required for local project coordination. Avoid logging tool arguments containing task tokens.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_projects` | Project IDs, stages and review counts |
| `get_project` | Direction, scenes, versions, reviews, timeline and work status |
| `get_workflow` | Pinned stage definitions and checks |
| `get_next_action` | Permitted stage, instructions, approved inputs and feedback |
| `claim_task` | Exclusive 15-minute task lease |
| `heartbeat` | Renew a still-valid lease |
| `get_artifact` | Exact version and registered local file paths |
| `register_artifact` | Copy produced files and save a new immutable version |
| `validate_artifact` | Structural, integrity and dependency checks |
| `submit_for_review` | Put a claimed version into the director's queue |
| `finish_task` | Complete a submitted handoff, or explicitly release the task |
| `save_scene` | Plan/revise package direction after the comic gate |
| `prepare_generation` | Export approved Wan prompt/reference request package |
| `export_project` | Portable ZIP of records and source files |

There is no approve, spend, upload-to-cloud or submit-to-Wan tool in v1.

## Example handoff

1. Call `get_next_action(project_id)`. If it says `awaiting_review`, report the waiting version and stop production at that gate.
2. Call `claim_task(project_id, agent_name="writing-agent")`. Project stages normalize `scene_id` to null. For scene stages, select the intended scene ID.
3. Produce the premise and register:

```json
{
  "project_id": "project_REPLACE",
  "payload": {
    "title": "Premise — option A",
    "kind": "premise",
    "stage": "premise",
    "content": "A complete readable premise goes here.",
    "prompt": "The exact writing/generation prompt goes here.",
    "inputs": [],
    "task_id": "task_FROM_CLAIM",
    "task_token": "TOKEN_FROM_CLAIM"
  },
  "file_paths": []
}
```

4. Call `validate_artifact(version_id)` and resolve issues. For a later stage, copy all pinned inputs returned by the task. Register files using explicit absolute paths, in reading/reference order. Media duration is measured on import.
5. Call `submit_for_review(version_id, task_id, token)` then `finish_task(task_id, token)`.
6. Tell the director which project and version are ready in the dashboard. Approval belongs to the director; do not alter SQLite to bypass it.

To revise an artifact, set `artifact_id`, `expected_version` to the current latest version ID, and include its complete new content/prompt/metadata/inputs. Existing files are inherited unless replaced by uploads or `inherit_files` is false. If inputs changed, reconcile them explicitly; a new version with old input IDs remains stale.

## Existing local audio tool

```powershell
.venv\Scripts\python.exe scripts/scratch_audio.py examples/timing-demo.json
```

Read the report and listen before requesting review. Register `mix.wav` first, then matching-length stems and cue/report files. Include `metadata.timing_passed`, `metadata.timing`, and the exact source script. The browser's Scratch audio dialog performs this local sequence as a background job.

## Extending the production system

Use `studio/agent_tools.py` for the shared implementation and expose new tools through `TOOLS`. Do not make the CLI and MCP separate business logic. Keep backend tests around dependency invalidation, leases and approvals. Add cloud job retries only after the reservation/receipt protocol in `WORKFLOW_SPEC.md` exists. An API timeout can be a successful paid submission with an unknown response.
