# Validation — Director Studio v0.1

Checked locally on Windows, 26 September 2026.

Publication verification on 29 September 2026: `npm run build` passed, and all 26 Python tests passed again with `DIRECTOR_DATA` pointing to a temporary directory and `DIRECTOR_NO_SEED=1`. Personal project records and generated media were excluded from the Git publication. The workflow PNG and editable diagram source were added to `docs/design/`.

## Automated checks

- `npm run build`: passed TypeScript compilation and Vite production build.
- `python -m unittest discover -s tests -v`: **26 tests passed**.
- Real MCP stdio client initialized the server, listed 14 tools, claimed a task, registered a premise, submitted it, finished the task, and confirmed that it remained awaiting human review. No approve tool was exposed.
- Core cases covered: concurrent claims, expired leases, creative-context changes, stage bypass attempts, conflicting version edits, timeline conflicts, cross-project source isolation, transitive stale dependencies, immutable source copies, file-hash corruption, upload duration inspection, range playback, timeline bounds, exact prompt/review exports, comic page requirements and Wan reference duration/order rules.
- Scratch audio cases covered: preserved overruns, unintended versus explicit overlap, boundary-crossing speech, isolated stems, saved versions and safe review-page text.
- `skill-creator/scripts/quick_validate.py .agents/skills/director-studio`: passed using the system Python with PyYAML.
- npm dependency audit reported zero vulnerabilities at install time. This is a point-in-time dependency check, not a security audit.

## Browser verification

Used separate QA records under `outputs/studio-browser-qa`, served temporarily on port 8768. User-facing projects on port 8767 were left unapproved.

- Created a new test project with a brief; saved a readable premise and its exact prompt.
- Approved the test-only premise with an explicit QA note; the next-action panel advanced to **Comic**.
- Edited the audio lab prompt into v2; v1 remained available with its original prompt and review state.
- Compared v1/v2 and saved feedback anchored at 6 seconds; it remained attached to v2.
- Ran scratch audio from the dialog with fresh dialogue. The background job completed and produced a new 15-second artifact in the review queue, with separate voice tracks and timing data.
- Added two playable ranges to the rough cut, saved them, and played the sequence. The player reached the second range's out point and paused with no media error. Browser hard-cut timing is approximate; this is not a mastered render.
- Imported the existing dashboard wireframe through the file chooser. The image preview decoded at its original 1586 × 992 size, with a source-file download and prompt panel alongside it.
- Verified scene direction content and workflow documentation in the app.
- Checked the desktop layout and 390px/768px viewport overrides. Document width stayed within the viewport; artifact/stage rails scroll internally on narrow screens. Reset the viewport afterwards. No browser console errors were reported during the QA flow.
- Restarted the user-facing app through `START_STUDIO.ps1`; the launcher reported the local service ready at port 8767, and the dashboard loaded the persisted technical lab.

## Precise limits

The checks establish a working local coordination and review tool. They do not establish:

- a human judgment that the sample audio performance or film story is good;
- automatic Blender scene creation, dummy animation or renderer execution;
- successful Alibaba authentication, reference hosting, paid Wan submission, or a generated Wan take;
- a seamless final video render, final audio mix or lip-sync result;
- multi-user authorization, public deployment, or an import/restore UI.

Those integrations and their contracts are described in `WORKFLOW_SPEC.md`. The current Wan operation exports a request package and provenance only. It does not make a network submission or spend credits.
