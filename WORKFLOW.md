# Approval workflow

The working dashboard and agent service implement this process. See [WORKFLOW_SPEC.md](docs/WORKFLOW_SPEC.md) for exact state rules and implementation boundaries, [AGENT_INTERFACE.md](docs/AGENT_INTERFACE.md) for reusable tools, and `workflows/comic-to-wan-v1.json` for the pinned machine-readable definition. This file retains the creative production guidance.

Provider: Alibaba Cloud Model Studio. Model: `wan3.0-video`. Default final generation unit: 15 seconds at 30 fps. A story scene may comprise any number of units. Use a shorter unit when the action benefits from it.

## Stages

1. **Premise:** propose ideas with a hook, cast, conflict, ending, tone and intended movie runtime. User chooses or revises an idea.
2. **Visual concept and comic:** establish initial character designs and an approved style sample, then create a readable 10-page comic. For a longer film, explicitly agree whether it is a condensed story or selected proof-of-concept scenes. User approves the comic before adaptation.
3. **Full screenplay:** develop the full narrative, then a timed shot list packaged into 15-second generation units. Preserve emotional beats and continuity across package boundaries. User approves script and structure.
4. **Temporary audio and timing:** synthesize each character separately, measure real dialogue duration, place reactions and silent action beats, and assemble the timeline. Review per clip and as a continuous scene. User approves the spoken timing before detailed boards and animation.
5. **Production references and boards:** create labeled character sheets, location/prop references and shot boards. Permanent character IDs must match the screenplay, temporary audio, reference images and colored Blender rigs. Export annotated review sheets plus clean image assets. User approves the boards.
6. **Blender preview:** animate simple rigged mannequins and rough sets against the approved temporary audio. Use camera moves, timing, eye lines and screen positions from the approved boards. Render each matching preview at 30 fps, up to 15 seconds. Maintain a clean picture-only preview and a separate review version with temporary sound. User approves the preview.
7. **Wan test and production:** test one representative approved package, including dummy-to-character mapping and timing fidelity, before larger batches. Review identity, actions, camera, audio and the join to neighboring clips. User approves each generation batch and its cost/retry allowance.
8. **Edit and finish:** assemble accepted takes, review continuity, replace or approve temporary voices, add sound/music, check synchronization and export the film. User approves the finished movie.

## Temporary audio contract

- Start with dialogue and explicit silence. Add temporary music/effects only when they affect timing, on separate tracks so they do not obscure dialogue review.
- A character keeps one scratch voice until a deliberate change. Scratch voice selection does not approve final casting.
- Give each line a timed slot. Measure the actual WAV; do not estimate timing from word count.
- Keep reaction beats and entry/exit pauses. Do not speed up or cut speech automatically to make it fit.
- If a line overruns, shorten it, move the action, change the package boundary, or divide the scene. Rebuild and review again.
- Keep an uninterrupted scene-level mix when reviewing several packages together. A generation boundary is not necessarily a visible cut.
- Final voices or regenerated Wan dialogue can change timing. Recheck synchronization and revise animation/editing when necessary.

## Approval records and revisions

Record the exact artifact/version, source hash, requested changes, and user's approval text. A technical test, successful render, silence, or script exit code never advances a creative stage.

Changes to script, character design, voice, pace or camera flag dependent work for review. Preserve previous versions. Retry paid generations only within an explicitly approved batch allowance. The technical demo has no creative approval.

## Current state

The temporary audio tooling is implemented. The movie remains at premise selection. No characters, comic, screenplay, boards, Blender scenes or paid generations have been approved or created for the movie.
