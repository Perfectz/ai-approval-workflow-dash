# Production workflow diagram

The [PNG](director-studio-workflow.png) is a 3687 x 2634 image exported with [Archify](https://github.com/tt-a1i/archify), version 3.0.1. The [structured JSON](director-studio-workflow.json) preserves the editable nodes, directed relationships, approval annotations and explanatory cards. Give an AI both files when exact wording matters.

Read steps 01-12 from left to right across each row, following the arrows between rows. The control row applies to every stage. Creative approval belongs to the director; a successful technical check is not approval. Revisions preserve earlier versions and flag affected dependent work for another review.

The current workflow plans 15-second generation/review packages, with 2-15 whole seconds allowed at 30 fps. Story scenes may span packages. Measure rendered speech, pauses and reactions before advancing to Blender or paid generation; preserve overruns and revise the timing draft.

## Current implementation

The local app implements project records, artifact versions, prompts beside previews, reviews, source pins, scratch-audio timing, rough cuts, shared agent CLI/MCP tools and Wan request-package export. External tools provide the creative assets that agents register in the studio.

Automatic Blender creation/rendering, reference hosting, paid Wan submission and final mastered-film rendering remain integrations to connect. The diagram describes the intended end-to-end process. A package can contain planning evidence that a provider does not accept directly; the provider adapter must map only supported inputs and validate current model capabilities before submission.

## Regeneration and validation

Install the Archify skill, then run its `finalize workflow` command against `docs/design/director-studio-workflow.json`, using the installed skill's instructions. Keep new render outputs and validation receipts under the ignored `.archify/` directory. Export the resulting HTML through **Export > PNG** and replace the documented PNG only after reviewing it.

The source diagram passed 9/9 showcase checks, strict HTML validation and real-browser checks, with zero errors or warnings. The light/dark captures and full-detail PNG were visually inspected on September 29, 2026. The PNG includes node annotations; supplementary timing and implementation-status cards remain in the structured JSON and these notes.

Local delivery receipts contain machine-specific paths and remain outside the published repository. The screenshot is a documentation snapshot; it does not update automatically when the workflow specification changes.
