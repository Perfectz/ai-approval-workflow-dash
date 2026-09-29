# Game sprite workflow through Google Flow

The **Game sprites** mode reuses the dashboard's exact-version review, source pins, prompts, task leases and portable exports. It adds an asset-oriented sequence: brief → design references → motion coverage → action boards → Google Flow clips → transparent sprites → game preview → delivery. The director reviews the exact prompt beside its inputs and outputs at each gate.

The workflow ID is `sprite-to-flow`, version `1`, defined in [`workflows/sprite-to-flow-v1.json`](../workflows/sprite-to-flow-v1.json). Film projects keep their existing workflow. In a sprite project, the existing scene records represent **animation entries**: typically one stable asset ID, action and viewing direction each. An animation entry is not a movie scene.

## Asset contract

Agree these before generating a design or motion clip:

| Decision | Record |
| --- | --- |
| Asset identity | Stable ID, role, approved silhouette, palette and reference version |
| Game view | Side view, top down or isometric; facing directions; fixed camera and projection |
| Output geometry | Cell width/height, displayed scale, padding, common pivot/baseline, texture filtering |
| Coverage | Required actions × directions; mirrored directions permitted only when visually valid |
| Motion | In-place or root translation, anticipation/contact/recovery, loop or one-shot, contact events |
| Timing | Flow source duration, selected usable range, sampled frame count, sprite playback fps |
| Engine delivery | Generic atlas or named engine, file naming, import settings, timing/pivot metadata |
| Generation allowance | Exact clean uploads, model, output count, attempts and credit cap approved with the action board |

Avoid a long source clip containing many unrelated actions. Start with one representative action and direction, approve its motion and extracted sprite quality, then expand coverage. A game walk cycle may use only part of a four- or eight-second Flow clip. Video duration, source video fps, extraction sample rate and sprite playback fps are separate values.

## Stages and approvals

| Stage / artifact kind | Scope | Output reviewed by the director |
| --- | --- | --- |
| `sprite_brief` / `sprite_brief` | Project | Asset contract and action/direction requirements |
| `sprite_design` / `sprite_design` | Project | Character/object design, actual-size sample, clean references and labeled identity sheet |
| `sprite_motion` / `sprite_motion` | Project | Coverage matrix, animation entries, motion beats, loop policy and extraction plan |
| `sprite_boards` / `sprite_board` | Animation entry | Labeled action boards, clean Flow references, exact prompt, reference map and credit/upload allowance |
| `sprite_flow` / `sprite_video` | Animation entry | Original downloaded clip, full motion playback and browser generation receipt |
| `sprite_sheet` / `sprite_sheet` | Animation entry | Transparent frames, atlas, timings/pivot manifest, contact sheet and loop preview |
| `sprite_engine` / `sprite_preview` | Animation entry | Actual-size playable result on game backgrounds; named engine import when requested |
| `sprite_delivery` / `sprite_delivery` | Project | Complete approved coverage and portable source/review archive |

Passing technical checks does not approve an artifact. The director decides through the dashboard; the agent tools expose no approval operation. Versions and original media are preserved. Changed approved references, prompts or direction invalidate affected downstream work so agents regenerate or reprocess against new source pins.

## Google Omni model and current capabilities

Official Google Flow documentation checked on September 29, 2026 names **Gemini Omni Flash 1.1**. It documents text, first-frame, first-and-last-frame and ingredient/reference generation at **4, 6, 8 or 10 seconds**, plus video editing up to ten seconds. Omni is documented at 360p draft and 720p standard resolutions. This mode defaults to an eight-second source clip and twelve fps sprite playback; those defaults serve different purposes. Do not apply the film mode's fifteen-second package length to Omni. [Google Flow model documentation](https://support.google.com/flow/answer/16352836?hl=en)

Model labels, available features and regional access must still be checked in the actual account's current UI. Keep `requested_model` distinct from the observed `selected_model`. Video source plans use landscape `16:9` or portrait `9:16`; square sprite cells are a separate output geometry decision. If the requested Omni model or required controls are unavailable, retain the prepared task and report the specific limitation instead of silently selecting another provider.

Google documents credits **per generation**, with requests sometimes producing more than one output. Check the displayed cost, output count and available allowance immediately before generating. Pricing is not hard-coded here. [Google Flow credit documentation](https://support.google.com/flow/answer/16526234?hl=en)

## Browser generation procedure

Video generation in this mode uses **Google Flow browser/computer control**, never a video generation API. No API key is needed for local coordination. The executing agent needs a supported browser-control capability with visible page inspection, upload and download, and an authenticated Flow session. Follow that capability's documentation. The director handles login or account challenges directly; the workflow does not collect credentials.

1. Read `get_project` and `get_next_action`, select the intended animation entry and `claim_task`. Read all pinned approved design, motion and board versions. Keep the lease token private and renew with `heartbeat` when needed.
2. Call `prepare_generation(project_id, scene_id)`. It returns a browser handoff containing exact prompt, pinned sources, local reference paths and the approved allowance. Preparation uploads nothing and spends nothing.
3. Open the user's Flow project or prepare a new project in the visible browser. Inspect the current page before every adaptive action. Select **Video** and the actual **Omni** model using current visible controls. Record the selected label, project URL, resolution, duration, aspect ratio, output count, reference mode and visible credit cost. Do not infer these from an old screenshot or an unobserved default.
4. Upload only the approved clean reference assets under the exact board version's upload permission. Add them in the intended order as frames or ingredients. Retain labeled boards for dashboard review. Google documents frame and ingredient workflows in its [video creation guide](https://support.google.com/flow/answer/16353334?hl=en).
5. Enter the approved exact prompt. Confirm fixed camera, requested action/direction, reference identity, full-body framing and background specification. Keep the standard prompt workflow when it provides the needed controls; do not ask the Flow Agent for multiple variations unless that batch is explicitly allowed.
6. Re-read source pins and allowance. Immediately before clicking Generate, call `reserve_flow_attempt` with the project, animation entry, live task ID/token, actual selected model and the displayed credit cost. Retain the returned attempt ID. The reservation is local and makes no Google request; it bounds approved attempts and credits.
7. Click Generate once for that reservation. Use `record_flow_result` to log observed status and evidence (`submitted`, `downloaded`, `failed` or `unknown`). Observe the existing generation until it completes or needs attention. A slow response, browser interruption or uncertain outcome consumes the reservation and does not authorize another click. Inspect project history for the existing result. Unresolved reserved, submitted or unknown attempts block a duplicate reservation. Do not purchase credits, change subscription or create a hidden paid retry.
8. Play the entire result. Check identity, silhouette, camera movement, foot contact, clipping, scale drift, unintended motion and action completion. Download the **original** result through supported Flow controls into a new version folder. Preserve failed and superseded takes as evidence. Measure the downloaded file rather than copying an expected duration. Log the downloaded result and its local filename; failure logging does not refund credits or authorize a retry.
9. Register the original clip first, then receipt/evidence files, as `sprite_video`. Include the exact prompt, references/source pins and `metadata.flow`. Run `validate_artifact`, submit that version for director review, then finish the task. Do not begin extraction until the clip is approved.

The software can reserve a browser attempt and validate a receipt, but the external Generate button remains controlled by the executing user or agent. Do not call a local reservation a completed or provider-verified generation. This application feature has been validated locally without spending Google credits.

### Reconcile an interrupted attempt

If Generate was clicked but the browser timed out before a clip appeared, record the existing attempt as `unknown` with the observed error and project URL. Keep checking that same Flow project/history through the visible browser; preserve screenshots and do not click Generate again. `reserved`, `submitted` and `unknown` attempts block a duplicate reservation.

While the original lease is valid, renew it with `heartbeat`. If it expired or was released, claim the same project's animation task and call `record_flow_result` to reconcile the existing attempt with current observations. The original task provenance remains in the record. Only record `downloaded` after downloading the actual result, or `failed` after observing a failure. Reconciliation spends nothing, refunds nothing and does not approve another attempt. Any later generation still needs a valid current approved package and remaining allowance.

### Board reference map and allowance

Include the clean inputs and their use in `metadata.reference_map`. `metadata.flow_references` identifies the ordered clean images explicitly; there is no fallback that uploads labeled boards. Each entry names a pinned approved source `version_id`, `file_index`, and `role` (`ingredient`, `first_frame` or `last_frame`). Use `version_id: "self"` for a separate clean image attached to this board version; preparation resolves it to the approved board's real version ID. The exact board's director review also covers `metadata.flow_allowance`:

```json
{
  "reference_map": "REF_01: clean approved CHAR_001 side-right design; REF_02: approved first contact pose. Labeled review board is not a Flow ingredient.",
  "flow_references": [
    {"version_id": "APPROVED_DESIGN_VERSION_ID", "file_index": 0, "role": "ingredient"},
    {"version_id": "self", "file_index": 0, "role": "ingredient"}
  ],
  "flow_allowance": {
    "max_generations": 1,
    "max_credits": 20,
    "outputs_per_generation": 1,
    "upload_authorized": true
  }
}
```

This example uses two clean ingredients. To use first/last frames instead, assign those roles to the corresponding clean files and select a coherent frame mode supported by the actual UI. Confirm the relevant local file indices before submission. These numbers illustrate an allowance, not a price quote or an approval. An agent registers this proposal; the director reviews the actual artifact version. Revising the prompt or reference versions requires renewed approval.

The shared local reservation arguments are `project_id`, `scene_id`, `task_id`, `token`, `selected_model` and `credit_cost`. Result logging takes `attempt_id`, `task_id`, `token`, `status`, `evidence` and optional `project_url`. These tools record local browser work and make no provider request. Keep their tokens out of media and generation receipts.

### Downloaded clip receipt

The clip version's `metadata.flow` records observed browser execution. Attach relevant settings and completion screenshots without private account details. Example structure:

```json
{
  "provider": "Google Flow",
  "execution": "browser_ui",
  "selected_model": "The exact label observed in the Flow model selector",
  "project_url": "https://labs.google/fx/tools/flow/PROJECT_FROM_UI",
  "generated_at": "ISO timestamp of the observed completed generation",
  "attempt_id": "job_RETURNED_BY_RESERVATION",
  "settings": {
    "duration": 8,
    "aspect_ratio": "16:9",
    "resolution": "720p",
    "outputs": 1,
    "reference_mode": "Frames"
  },
  "evidence": "settings.png shows model, length and output count; completed.png shows the generated clip. Original downloaded as walk-right-take-001.mp4."
}
```

Add observed credit cost, original asset/generation identifiers when shown, download filename and any browser errors to the receipt. Avoid placeholder receipts in real project records. The registration tool measures local media metadata and stores exact file hashes; receipt text alone does not prove generation occurred.

## Local sprite processing

Google Flow outputs motion footage. It does not guarantee transparent alpha, stable per-frame pixel art, a usable loop or engine-ready pivots. Treat the clip as a motion source. For extraction, first approve an explicit usable interval and the frame sampling/playback plan. Preserve the downloaded original and write derived output into a new folder.

For coordinated agent work, prefer `extract_sprites(project_id, scene_id, source_version_id, settings, task_id, token)`. Claim the `sprite_sheet` stage first and pass the current approved clip version. This shared helper runs local processing and registers a new version with exact inputs, file indices and the real QC report. Geometry and timing must match the approved animation entry; revise the plan and obtain its approvals before changing them. The helper does not submit or approve its result. Inspect the output, then run `validate_artifact`, `submit_for_review` and `finish_task` normally.

Run the local processor with a settings file:

```powershell
.venv/Scripts/python.exe scripts/pack_sprites.py --source C:/project/walk-right-take-001.mp4 --output C:/project/walk-right-sprites-v1 --settings examples/sprite-animation.json
```

Use real project paths and adjust the example before a production run. Required settings are `start_seconds`, `end_seconds`, `frame_count`, `cell_width` and `cell_height`. Options include `sprite_fps`, `loop`, atlas `columns`, `padding`, `background_key`, `key_tolerance`, `feather`, `pixel_art`, normalized `feet_pivot`, optional `source_anchor` and common `scale`. The example requests a one-second twelve-frame loop; it is a processor settings example, not evidence of an approved animation.

Sampling uses `start + i * (end - start) / frame_count` and excludes the duplicate end boundary. The source interval and sample times remain in the manifest. The processor applies one common crop, scale and source anchor across all frames. This preserves intended bobbing and relative motion rather than independently shifting every frame to its own detected bottom edge.

Use a chroma background absent from the asset palette when planning Flow references; keying should be reviewed for holes, fringes and motion blur. Setting `background_key` to `null` preserves source alpha. A solid opaque video without keying remains opaque. `pixel_art: true` uses nearest-neighbor resizing; this cannot repair an inconsistent silhouette or turn arbitrary rendered footage into deliberate pixel art.

Outputs:

| File | Purpose |
| --- | --- |
| `source.<extension>` | Preserved original and hash recorded in the manifest |
| `raw-frames/frame_0001.png` | Original sampled frame sequence |
| `frames/frame_0001.png` | Fixed-cell processed RGBA frames |
| `sheet.png` | Transparent atlas |
| `atlas.json` | Geometry, pivots, frame durations, sample times and source provenance |
| `animation.gif` | Animation preview; PNG alpha remains the authoritative asset |
| `extraction.json` | Source metadata and planned sample times, retained if later processing fails |
| `qc.json` | Technical warnings such as empty/duplicate frames, edge contacts and loop discontinuity |

Technical QC does not certify identity, the intended action or a convincing loop. Review the atlas/contact sequence, full playback and alpha over light and dark backgrounds. Check common scale, baseline/pivot, cropping, foot contacts, the loop seam and timing. Correct or repaint bad frames in a new version; do not conceal a broken loop by silently omitting required poses. Register the sheet, frames, manifest and preview as one `sprite_sheet` version with extraction settings and the approved clip source pin.

For a shared-tool import, a useful file order is `sheet.png`, `animation.gif`, `atlas.json`, `qc.json`, then the processed frames and source/extraction evidence. Record `metadata.sprite.sheet_file_index` and `metadata.sprite.atlas_file_index` against that exact order (here `0` and `2`), plus `metadata.sprite.qc` containing the actual parsed processor QC report. Do not hand-write a passing QC result. The frame count must match the approved animation entry. Preserve warnings for director review even when structural checks pass.

## Preview and delivery

Register an actual playable `sprite_preview` with readable usage notes and `metadata.engine_notes`. Preview at game size with the declared fps and loop/one-shot policy. Compare transitions to neighboring actions, contact events and anchoring. A generic browser sprite player is useful evidence; identify it as generic. A Godot, Unity, Phaser or other named engine deliverable requires an actual import and playback check in that engine before claiming it works there.

Final `sprite_delivery` covers the approved action/direction matrix, stable filenames, frame and atlas PNGs, source timings, pivots, events, filtering/import notes, playable previews and licenses/attribution. Keep original Flow clips, prompts, settings and reference versions. Registered sprite output includes `metadata.sprite.bundle_file_map`, which retains source relative filenames despite immutable artifact storage naming. `export_project` writes a portable `sprites/<scene_id>/<version_id>/` bundle with `sheet.png`, `atlas.json`, `frames/` and associated files alongside the review/provenance archive. Engine packaging can sit alongside it. Publishing a game or uploading assets is a separate action from local asset delivery.

## Agent handoff

The reusable skill is [`.agents/skills/flow-sprite-studio/SKILL.md`](../.agents/skills/flow-sprite-studio/SKILL.md). It uses the same shared CLI and MCP as film projects. Query `get_workflow` with the actual `project_id`, or `workflow_id: "sprite-to-flow"` for a workflow-only query. Its no-argument form retains the film default. `get_next_action` determines permitted work, `claim_task` protects it, and `register_artifact` pins exact source versions. Use `get_artifact` to obtain absolute local paths. Keep lease tokens out of prompts, exports and evidence screenshots.

If capabilities are missing, leave a concrete prepared package and report whether the blocker is login, browser upload/download support, actual Omni availability, reference approval or generation allowance. The browser handoff makes an agent-ready task; it does not establish that a live Google generation was run.
