# Director Studio — workflow specification

Version 1 · Local application · 26 September 2026

Director Studio keeps a film's creative intent, production artifacts, prompts and review decisions together. A human directs the work through the dashboard; different agents use the same project records through CLI or MCP. This document describes the working implementation and the contracts for later automation.

## 1. Production structure

Project → scene packages → artifacts → immutable content versions → review events.

A narrative scene may span several generation packages. A package is 2–15 whole seconds at 30 fps. Shots inside it can have natural lengths; package boundaries need not become visible edits. Plan entry/exit states and usable edit handles in the script. The runtime target is a planning target, not an instruction to stretch every shot to 15 seconds.

Each project records a brief, target runtime, aspect ratio, creative locks, world notes, voice direction, delivery notes and a planning budget. Each scene package records dramatic purpose, emotional turn, start state, end state, locked decisions, flexible decisions and performance notes.

`workflows/comic-to-wan-v1.json` is the machine-readable workflow. Projects pin its ID and version. Later workflow changes should use a new version and an explicit migration; do not reinterpret existing approvals by editing v1 in place.

## 2. Review gates

| Gate | Required artifact | Scope | Director checks |
| --- | --- | --- | --- |
| Premise | Readable premise | Whole project | Hook, audience, cast, conflict, ending and emotional intent |
| Comic | Exactly 10 page images | Whole project | Complete readable story, consistent visual direction and character identity |
| Script | Readable screenplay | Whole project | Full narrative, dialogue, camera/action plan and scene packages |
| Audio | Playable temporary mix and timing report | Each package | Performance space, natural pauses, action beats, no unintended clipping/overlap |
| Boards | Storyboard images and reference mapping | Each package | Composition, action, character/prop IDs, eye lines, screen direction and continuity |
| Blender | Playable preview and editable `.blend` | Each package | Camera, blocking and movement against approved timing; dummy identity mapping |
| Wan | Generated video take | Each package | Identity, performance, action, audio, lip sync and neighboring cuts |
| Edit | Playable finished film | Whole project | Continuous playback, pacing, sound, delivery formats, rights/credits and captions |

Technical checks are deliberately narrower than creative review. The service checks file integrity, required file types, source versions, scope, comic page count, timing reports and measured media duration. It cannot establish that a comic is good, a face is consistent or a generated performance is correct. The stage's human checklist remains visible in the workflow guide.

The imported **Temporary audio lab** is clearly marked as a sandbox. It lets you review technical audio without inventing an approved movie premise. User-created film projects cannot enable that bypass through the dashboard.

## 3. Version and approval rules

States: `draft → in_review → approved` or `changes_requested`. Comments are separate events. Versions whose inputs changed display `needs_update` while preserving the original approval and feedback history.

- Edits make a new numbered content version. Old files, prompts, notes and reviews remain available. Submission changes workflow state; it does not replace content.
- Every dependent version pins exact upstream version IDs. Same-project inputs only. Required deliverables must include their approved upstream sources before passing review.
- A newer draft does not replace a still-approved version. Approving a newer source makes descendants pinned to the old version stale, including transitive descendants.
- Scene direction edits invalidate artifacts built against the earlier scene revision. Changes to the project brief, creative locks, world notes or voice direction invalidate versions built under the old creative direction. Budget and title edits do not invalidate creative work.
- A stale artifact needs a revised version and a new review. Explicitly choose the current source versions after reconciling changes. Nothing is automatically regenerated or deleted.
- Updates carry `expected_version` or `expected_revision`. A competing edit receives a conflict instead of silently overwriting someone else's work.
- An agent can prepare, check and submit work. The agent interface has no approval operation. The director's dashboard records approval for the exact version selected.
- Approval does not authorize paid generation. In this release there is no paid submission operation at all.

This is a trusted, single-user local application. The separation between agent tools and director review is a workflow boundary, not a security boundary against an agent with unrestricted filesystem access. Do not expose the server on a network without authentication, authorization and deployment hardening.

## 4. Artifact contract

Each artifact has an ID, project, optional scene, kind, stage and title. Each version stores readable content, exact generation prompt, ordered files, metadata, source version IDs, author, creation time, direction snapshot hash and content hash. Every registered file has a SHA-256 hash and is copied into the version's asset directory.

Example registration payload:

```json
{
  "title": "Opening — storyboard package",
  "kind": "storyboard",
  "stage": "boards",
  "scene_id": "scene_REPLACE",
  "content": "Purpose, shot notes and the director's viewing guide.",
  "prompt": "0–6s: ... 6–15s: ... Image 1 establishes CHAR_A ...",
  "inputs": ["version_APPROVED_SCRIPT", "version_APPROVED_AUDIO"],
  "metadata": {
    "reference_map": "CHAR_A → blue dummy → identity sheet A; CHAR_B → orange dummy → identity sheet B",
    "prompt_extend": false,
    "shots": [
      {"id": "SHOT_01", "start": 0, "end": 6, "camera": "Wide, 35mm, static", "action": "CHAR_A enters from screen left"},
      {"id": "SHOT_02", "start": 6, "end": 15, "camera": "Medium on CHAR_B", "action": "CHAR_B reacts and replies"}
    ],
    "reference_media": []
  }
}
```

This is a shape example, not valid project data: use the actual IDs and all required inputs returned by the service. Metadata is extensible JSON; fields such as shot geometry and voice IDs are production contracts for the agent, not automatically interpreted Blender commands in this release.

Store labeled review boards and clean model input frames separately. The review sheet should explain who is who; the submitted image should not accidentally bake labels, arrows or watermarks into the film. A character reference artifact can hold front/side views, expressions, costume and prop details. Record permanent character IDs and explicitly link approved reference artifacts through `inputs`.

## 5. Temporary audio and timing

The dashboard runs the existing local `scripts/scratch_audio.py` generator as a background job. It synthesizes plain text with Windows System.Speech, then measures PCM samples. The interface starts from `examples/timing-demo.json`; the full JSON editor exposes casts, voice rate, shot boundaries, action intervals and generation packages.

Outputs include the mix, separate character stems, measured line start/end/duration, silence/action timing, subtitles and Blender timing markers. The first playable file is the primary preview and its measured duration is the artifact duration. Other tracks should cover the same package; do not mix different-length takes into one artifact.

If a line exceeds its slot, crosses a generation boundary, or overlaps unintentionally, the full line is preserved. The version remains a draft requiring changes; reference slices are withheld. A passing version enters the review queue without creative approval. Restarted local synthesis jobs become `interrupted`; no hidden automatic retries.

Temporary voices establish timing, not final voice identity. An adapter for final speech/lip sync must retain voice IDs, delivery direction, pronunciation, intended line timing and the original dry audio. The director must decide whether to retain final audio externally, use model-generated audio, or run a separate lip-sync pass.

## 6. Blender and Wan handoff

The current release accepts and reviews Blender artifacts and prepares Wan request packages. Agents create/render the actual Blender scene with their available tools. The dashboard does not yet generate camera rigs or animate dummies automatically.

For a Blender handoff, include the editable `.blend`, a picture-only preview, optional review preview with labels/audio, a character-color map, camera/shot details and timed action notes. Use the same coordinate conventions and persistent character IDs across packages. At 15 seconds and 30 fps the reference is 450 frames; verify the exported duration, not only Blender's frame range.

`prepare_generation` requires current approvals for the scene's audio, boards and Blender artifact. It chooses a non-empty prompt from approved previs, falling back to approved boards. It reads ordered `metadata.reference_media` entries with `type`, `url` and a measured `duration` for audio/video. The exported `model`, `input`, and `parameters` are the request body; `provenance`, readiness and explanatory fields are local records and must not be sent as provider parameters.

The adapter targets Alibaba Cloud Model Studio's `wan3.0-video`. Its endpoint uses the actual workspace and region. The reference mode, allowed counts, duration constraints and explicit `prompt_extend` setting are based on the [official Wan 3.0 API reference](https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference), checked 26 September 2026. See `WAN_AND_AUDIO.md` for the provider limits. The current exporter deliberately accepts HTTPS references only and supports the image/video/audio reference mode used by this workflow.

**The exporter does not prove remote URL accessibility or that a URL contains the approved local asset.** Before submission, the hosting adapter must map each URL to the exact approved local file hash, validate its media constraints, and show the final ordered package for review. Hosted URLs are not created by this app. Do not call a package production-ready solely because its schema checks pass.

Future paid-job implementation contract:

1. Confirm workspace, region, model, credentials, approved versions, uploaded source hashes and final request hash.
2. Record explicit permission for this package, maximum attempts and maximum total cost. Re-check current pricing; include reference-video billing where applicable. A project planning budget is not spending permission.
3. Write a durable local submission reservation before the network request. Persist provider task ID immediately. A timeout after submission is an unknown outcome to reconcile, not an automatic retry.
4. Poll that same task ID; do not duplicate it. Persist status, receipt, usage, known cost and actual request. Expiring provider URLs are not permanent storage.
5. Download successful takes promptly through the authorized adapter, register immutable files, and send the result to review. Keep failures and rejected takes in history. Cancel/retry only within the recorded allowance.

No credentials, upload, paid request, or Wan generation was performed to build this tool.

## 7. Agent coordination

CLI and stdio MCP expose identical operations through `studio/agent_tools.py`. Agents acquire a 15-minute lease for a project stage or scene-stage pair, renew it during long work, register a version, submit it, then complete the handoff. SQLite transactions ensure only one agent wins a competing claim. Expired leases do not authorize writes. An upstream input change invalidates the claim.

Read `AGENT_INTERFACE.md` and `.agents/skills/director-studio/SKILL.md`. The skill is portable within the project. An MCP client can launch the server without the dashboard running, because both use the same database directory. Never run different clients against accidental separate copies of the data; configure `DIRECTOR_DATA` consistently.

## 8. Review and editing

The main desk shows an artifact preview, editable prompt/reference map, selected version and review panel together. Image packages support page navigation. Audio has selectable stems and measured waveform/cues. Videos use range requests for seeking. Compare shows an earlier version and its saved prompt. Feedback can target a timecode or page/frame.

The film timeline selects exact version/file pairs, usable in/out ranges and clip order. It can include draft takes for comparison, with their status visible. Saving validates source project and media bounds. The browser plays hard cuts in order; it is a rough-cut reviewer, not a frame-accurate mastering engine. Transition rendering, multiple audio buses, ripple editing, subtitles burn-in and final MP4 assembly are future edit-adapter work. Final delivery still requires approved sources and whole-film human review.

## 9. Storage, portability and operating model

- React/Vite frontend; FastAPI service; SQLite in WAL mode; local immutable source files.
- Runtime state: `studio-data/studio.sqlite`, `studio-data/assets/`, `studio-data/work/`, `studio-data/exports/`.
- Local server binds to `127.0.0.1`. Director mutations need a same-session token; unrecognized hosts and cross-origin requests are rejected. Uploaded active HTML/SVG/scripts are not served as artifacts.
- Export ZIP contains project data, all source versions/files, prompts, review history, pinned workflow and editable timeline. Exports are portable records; an import/restore UI is not yet implemented.
- For a complete workspace backup, stop the server and MCP clients, then copy the whole `studio-data` folder. SQLite WAL files must be preserved if copying while open; prefer a stopped backup. Do not commit runtime data or credentials to Git.
- This release has one human director and multiple local agents. Multi-user accounts, shared cloud storage, remote workers, durable cloud job scheduling and public deployment are outside v1.

## 10. Acceptance criteria

Create a project; save and review a premise; observe the next gate; register files with prompts; preserve revisions; see the old decision retained; change an approved input and see affected work marked stale; import playable media and seek; generate scratch dialogue; save and replay a rough-cut order; export the project; complete a claim/register/submit handoff through MCP without any approval tool.

Automated tests cover these service invariants plus source isolation, conflicting edits, range responses, lease expiry and timing overrun preservation. Browser verification covers the actual creation, editing, review and audio flows. See `VALIDATION.md` for the checked result and remaining integration limits.
