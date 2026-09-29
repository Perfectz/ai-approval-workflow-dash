---
name: flow-sprite-studio
description: Create game sprite animation assets through the shared approval dashboard, using Google Flow and Gemini Omni by browser or computer control, then local frame extraction and sprite packaging. Use for asset design, motion plans, Flow clips, transparent sheets and game previews in this repository.
---

# Flow Sprite Studio

Use the project database as the handoff authority. This mode turns approved game asset designs into controlled motion clips in **Google Flow's visible browser UI**, then into reviewed transparent sprites. Video generation uses browser or computer control, not an API. Read [the sprite workflow](../../../docs/SPRITE_WORKFLOW.md) for asset contracts, provider checks, processing and receipts; read [the shared agent interface](../../../docs/AGENT_INTERFACE.md) for CLI/MCP argument forms.

## Coordinate one approved stage

From the repository root, call shared CLI tools with `.venv/Scripts/python.exe -m studio.cli TOOL --json-file request.json`, or use the matching stdio MCP tools. Begin with `list_projects`, `get_project`, `get_workflow(project_id)` and `get_next_action`. A workflow-only query can use `get_workflow(workflow_id="sprite-to-flow")`; no arguments retain the film default. Confirm the project uses `sprite-to-flow`; scene records in this mode are **animation entries**, each identifying an asset, action and direction.

Read current feedback and every pinned source version. If the action is awaiting review, return the exact version to the director. Otherwise `claim_task`, keep its token private, and `heartbeat` during long work. Produce against the pinned inputs and stable asset IDs. Register a new immutable version with the task ID/token, exact prompt, ordered references, metadata and absolute file paths. Revisions need `expected_version`. Run `validate_artifact`, fix structural issues, then `submit_for_review` and `finish_task`. A successful tool run is never creative approval; agents have no approval operation.

An upstream design, direction or motion change makes affected downstream work stale. Refresh state and redo only that affected work against new approved inputs. Do not manufacture approval by changing the database or calling private review routes.

## Use Google Flow through the browser

Before the Flow stage, read [the browser procedure](../../../docs/SPRITE_WORKFLOW.md#browser-generation-procedure). The session must provide a supported browser/computer-control tool with visible-page inspection, file upload and download, plus an authenticated user session in Flow. Read that tool's documentation and use its supported controls. If login, upload, download, model access or credit allowance is missing, preserve the prepared task and report what the user needs to supply. Do not replace the chosen provider with an API or a different model.

`prepare_generation` returns an approved browser handoff; it does not generate, upload or spend. Inspect actual controls and record the selected model label. Google officially documents **Gemini Omni Flash 1.1**; availability, settings and costs must still be checked in the current UI. Distinguish the user's requested model name from the actual selected one. Use clean approved reference images; keep labeled action boards in the review package.

The approved `sprite_board` version must include `metadata.reference_map`, ordered `metadata.flow_references` pointing to clean image file indices, and `metadata.flow_allowance` with upload authorization, output count, maximum generations and maximum credits. Immediately before Generate, verify the exact prompt, source pins, reference order, supported duration, resolution, aspect ratio, output count and that allowance. Call `reserve_flow_attempt` using the live task ID/token, actual selected model and visible credit cost; record its returned attempt ID. This local reservation sends nothing to Google. Each additional output or retry can consume credits. Use `record_flow_result` to log the observed status and evidence. An uncertain or pending result does not authorize another request or refund the reservation. Preserve every original downloaded take and settings/evidence receipt. Register the clip as `sprite_video` with `metadata.flow`, submit it for review, and stop at that gate.

If the UI times out after Generate, log `unknown`, inspect the existing Flow project/history and preserve that attempt's evidence. Renew a live lease. After a lease expires or is released, claim the same animation's permitted task and use `record_flow_result` to reconcile the existing attempt with observed evidence. Reconciliation preserves original task provenance and does not authorize a new generation or restore the allowance.

## Convert approved motion into sprites

Read [local sprite processing](../../../docs/SPRITE_WORKFLOW.md#local-sprite-processing) only when the clip is approved. Keep video length, extraction sample rate, sprite playback rate and loop cycle as separate values. Use one crop/scale and common pivot across frames; preserve the original clip. Do not promise transparent video or exact pixel art from Flow. Background removal, edge cleanup, silhouette consistency and loop seam need review.

Prefer shared `extract_sprites` with the claimed task ID/token, current approved clip version and approved settings. It creates the local output and registers a `sprite_sheet` version with exact inputs and QC; it does not submit or approve that version. The standalone processor is useful for a separate local processing run, followed by explicit registration. Geometry and timing must match the approved animation plan.

Produce transparent frame PNGs, atlas PNG, timing/pivot manifest and an actual-size preview. Review full playback and alpha on contrasting backgrounds. Label a generic browser preview accurately; claim a specific engine integration only after importing and testing there. Submit sheets, previews and final delivery as separate approved stages. Export the project to preserve prompts, references, decisions and source versions alongside the game assets. Registered sprite bundles preserve their relative layout through `metadata.sprite.bundle_file_map`; portable exports include `sprites/<scene_id>/<version_id>/sheet.png`, `atlas.json` and `frames/`.
