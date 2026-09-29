---
name: director-studio
description: Work through an existing Director Studio film project using its shared CLI or MCP tools. Use for idea, comic, screenplay, scratch audio, boards, Blender previs, Wan reference preparation, and artifact handoffs in this workspace.
---

# Director Studio

The project database is the handoff authority. Read it instead of reconstructing production state from chat. The dashboard and agent tools share the same service rules and local files.

From the repository root, use `.venv/Scripts/python.exe -m studio.cli TOOL --json-file request.json`, or the identically named tools in the Director Studio stdio MCP server. Read `docs/AGENT_INTERFACE.md` for argument examples. Start with `list_projects`, `get_project`, and `get_next_action`. Do not choose a film from its title alone when the user's target is ambiguous. The imported audio lab is a technical sandbox.

## Work one approved step at a time

1. Read the current direction, latest director feedback, and every pinned source version returned by `get_next_action`.
2. If state is `awaiting_review`, hand the exact version back to the director. Do not treat a passing check as approval.
3. If work is ready, `claim_task` with an identifiable agent name. Select a scene for scene-scoped stages. Keep its lease token out of prompts, media, exports, and comments. Renew with `heartbeat` for long work.
4. Make the deliverable using the generation/rendering tools authorized and available in this session. This skill supplies workflow coordination, not an image or video model. Preserve permanent character IDs, scene intent, continuity state, and creative locks.
5. `register_artifact` with exact prompt, ordered references, metadata, pinned inputs, and the task ID/token. Updates require the latest `expected_version`; never overwrite source files. Import files in their intended reading/reference order. Readable ten-page comic and video storyboard are different artifacts.
6. Run `validate_artifact`, then `submit_for_review`. Fix structural failures; preserve overrun dialogue for diagnosis. `finish_task` only after submission, or release the lease if stopping without a handoff.

The agent interface has no approval tool. A director decision is recorded through the dashboard. User delegation in chat should be explained and recorded explicitly; never forge a director approval by editing SQLite or calling private approval routes. A changed source invalidates downstream approvals. Refresh the task and rebuild only affected work.

## Production details

- Packages use 2–15 whole seconds, 30 fps. A package may contain several natural shots; film scenes can span packages.
- Scratch audio: `scripts/scratch_audio.py` writes measured mixes, isolated stems and cue sheets. Read `examples/timing-demo.json`; the dashboard also runs this tool. Temporary voices are not a final voice contract.
- Boards: keep clean model inputs separately from labeled review images. Include cast/prop IDs, screen direction, eye lines, action timing, clean reference files and `metadata.reference_map`.
- Blender: create editable `.blend` plus a picture-only preview from the approved boards and timing. Map dummy colors to permanent character IDs. Do not claim Blender motion guarantees Wan fidelity. Record shots, camera transforms and action keyframes in metadata or a JSON attachment.
- Wan: `prepare_generation` validates a reference package but sends no paid request. Use only the exported `model`, `input`, and `parameters` as the eventual API body. Before an external adapter submits, verify current provider docs, region/workspace/key, hosted media, exact approved package and attempt/cost allowance. Persist task ID immediately and poll; an ambiguous timeout is not permission to duplicate the task.
- Final review includes complete playback and neighboring cuts. A technically valid MP4 is not proof of a coherent film.

Read `docs/WORKFLOW_SPEC.md` for implementation boundaries, state rules, source schemas and delivery requirements. Do not promise integrations listed there as future work.
