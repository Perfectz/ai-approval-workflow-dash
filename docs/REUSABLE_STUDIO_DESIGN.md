# Reusable video studio — design proposal

Status: proposed architecture, not an implemented production system. The existing temporary audio tooling is working. The dashboard concept is a separate interface preview; its sample records and simulated approvals do not modify project state.

## Product

One local studio manages multiple movie projects. A reusable workflow defines the production stages. Agents use a common tool interface to find approved inputs, perform one eligible task, register versioned outputs, run checks and request review. The dashboard is the user's artifact viewer and approval surface.

The first workflow preset is comic-to-Wan: premise → visual concept / 10-page comic → screenplay → temporary dialogue timing → character references / storyboards → Blender preview → Wan generation → final edit. Default video generation unit is 15 seconds. Scenes can contain multiple units and shots.

## Three distinct responsibilities

1. **Workflow definition:** stage inputs, deliverable types, validation, dependency rules and human review requirements. Store versioned JSON plus readable instructions. Pin each project to a workflow version; migrating an existing project is an explicit operation.
2. **Project service:** authoritative state, immutable artifact versions, approvals, feedback, work claims, job receipts and dependency tracking. Agents and the dashboard call this service; they do not independently edit status files.
3. **Dashboard:** project navigation, current review queue, artifact browsing, side-by-side comparisons, inline playback, reference packages and user decisions. It displays the service's state.

The first version runs on this Windows computer. Store metadata in SQLite and large media as ordinary files. A Python service keeps integration with the working audio scripts straightforward. Use a typed web frontend for viewers and review interactions; framework choice is secondary to the shared data contracts. Host an MCP adapter and a CLI over the same service functions. Do not duplicate workflow logic in each client.

SQLite is suited to application data and portable local storage: [SQLite application file format](https://www.sqlite.org/appfileformat.html). MCP exposes tools/resources to compatible AI hosts: [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture). These support the proposed design; neither automatically implements workflow enforcement.

## Records

| Record | Contents |
| --- | --- |
| Workflow version | Stages, input contracts, required outputs/checks, review rules. |
| Project | Brief, workflow version, cast/world references, settings and current stage. |
| Scene / sequence / shot | Narrative scene, generation package, camera shot, timing and ordering. |
| Artifact | Stable ID, kind, project and scene associations, title, current candidate version. |
| Artifact version | Immutable file set, content hashes, MIME types, exact input version IDs, creator, prompt/model/settings and creation time. |
| Validation | Check identity/version, target artifact version, pass/fail, evidence and warnings. |
| Review | Reviewer, exact artifact version or package manifest, decision and feedback. |
| Work item | Task type, required inputs, owner/lease, status, attempt and outputs. |
| Generation job | Provider job ID, request hash, submission state, media mapping, cost and outputs. |
| Event | Durable history of changes, attribution and timestamps. |

Keep artifact content state, technical validation and creative review separate. A file may pass timing validation while awaiting review. Approval belongs to one immutable version, never a mutable filename.

## Dependency changes

When screenplay v3 becomes v4, versions created from v3 remain available with their historical decisions. They are marked as requiring review against the new approved inputs. Readiness is recomputed from pinned input versions, approved references and required checks. Only affected branches become stale; changing shot 07 should not invalidate an unrelated scene.

The UI distinguishes latest draft, last approved version, superseded version and downstream work needing review. It never silently switches a generation package to newly edited references.

## Agent interface

The instructions explain how to work; the service enforces legal transitions and writes records. Bundle a discoverable skill/playbook, reference schemas, command examples and a small adapter for each supported agent host.

Proposed tools:

- `list_projects`, `get_project`, `get_workflow`: identify scope and requirements.
- `get_next_action`: return one eligible task, pinned input versions, relevant files, acceptance checks, approval boundaries and output contract.
- `claim_work`, `heartbeat_work`, `release_work`: prevent two agents performing the same task; expired leases can be recovered deliberately.
- `register_artifact`: ingest completed files into a new immutable version; validate file existence/type and record provenance.
- `run_checks`, `submit_for_review`: produce evidence and queue an exact review package.
- `get_feedback`: retrieve revisions, including page/panel/shot/timecode anchors.
- `prepare_generation`, `get_job_status`: validate an approved package and follow durable provider jobs.
- `export_package`: export the prompt, media, ordered provider references and readable instructions for manual use.

Do not expose a general agent-side `approve` tool. Human approval is recorded through the dashboard's dedicated user channel. Ordinary agent clients may request review; they cannot satisfy their own approval requirement. Chat approval can be supported later with an explicitly user-initiated confirmation linked to the exact version.

CLI operations return structured JSON and meaningful exit codes. MCP hosts get typed tools and artifact resources. An agent that cannot call MCP but can run local commands can use the CLI. A remote/cloud agent needs an authenticated connection or exported package; localhost tools are not automatically available remotely.

## Work execution and recovery

Use transactional work claims and optimistic revision checks on state changes. A stale agent cannot overwrite a newer version. Stage outputs in an attempt directory, hash them, then register them atomically. Orphaned files do not advance a stage. Partial or failed runs retain evidence without appearing complete.

Run long jobs in a durable worker queue outside the HTTP request. Record provider IDs immediately after submission. On an uncertain submission, reconcile before retrying; do not assume remote exactly-once behavior. Reopening the dashboard or switching agents resumes known work. All downstream starts recheck the inputs and approvals they depend on.

## Dashboard

- **Projects:** title, current stage, cover if available, and the concrete action awaiting the user. No invented completion percentages.
- **Project workspace:** ordered stage navigation, current deliverables and the next eligible task.
- **Artifact viewer:** readable scripts/prompts, comic page reader, reference gallery, playable audio/video and version comparison. Blender files are accompanied by rendered MP4s/stills so reviewing never requires opening Blender.
- **Scene workspace:** screenplay excerpt, dialogue timing, storyboards, references, preview, exact Wan prompt and generated takes linked to a 15-second package. Support continuous playback across neighboring packages.
- **Review queue:** approve or request changes on the exact displayed version/package. Feedback can point to a page, panel, shot, frame or timecode.
- **Activity/jobs:** which agent is working, what it is producing, provider status, failed attempts, known costs and approved retry allowance. Do not invent progress when only queued/running is known.

Every viewer shows status, version and source dependencies. Drafts and approved versions remain easy to distinguish. Technical failures explain what to fix; missing media display a useful empty state. Prompt text is selectable/copyable and generation packages can be downloaded even when generation is manual.

## Storage and portability

```text
studio/
  workflows/comic-to-wan/v1/
  data/studio.sqlite
  projects/<project-id>/
    brief/
    assets/<artifact-id>/<version-id>/
    scenes/<scene-id>/
    runs/<run-id>/
    exports/
```

SQLite is authoritative for state. Readable JSON manifests, project status summaries and agent handoffs are derived exports, not competing state stores. Back up the database with a consistent SQLite backup operation and copy the referenced immutable media. Export projects with relative paths and a manifest so the destination can verify hashes and restore them. Keep credentials outside artifacts and exports.

Serve only registered project artifacts through media routes. Validate path scope and artifact associations rather than exposing arbitrary filesystem paths. Treat imported HTML as untrusted: sandbox it or generate a safe preview. The production service uses distinct user and agent capabilities; a skill file is not a security boundary.

## Existing component migration

Wrap `scratch_audio.py` as the first worker. It already produces source snapshots, WAV takes, stems, subtitles, timing evidence and a Wan preparation plan. Register those outputs as one versioned timing package. Preserve the current standalone entry point as a supported CLI path, but the integrated workflow gets approvals from the service instead of the current placeholder JSON fields. Replace the current unrestricted localhost file server with registered artifact delivery in the full dashboard.

## Delivery order and acceptance

1. **Reusable project core + dashboard:** create two isolated projects from the preset, register/view artifacts, compare versions, record user reviews and show the next permitted action. Import the existing timing demo. Verify an approval on one version never approves a newer version or another project.
2. **Agent tools + scratch audio worker:** prove Agent A can claim/create a timing artifact, stop, and Agent B can resume from durable state without chat history or duplicate work. Expose the same operations through CLI and MCP. Test a script change marking only dependent outputs stale.
3. **Reference packages + Blender worker:** generate scene assets from approved timing, render viewable previews and validate camera/character mappings. User reviews the rendered result.
4. **Wan worker + edit assembly:** prepare/validate exact reference packages, show cost/batch approval, submit and resume jobs, compare takes and assemble accepted footage. Confirm timing/identity fidelity with an approved test before scaling.

The first useful release is complete when two different agent clients can safely hand off one project while the user can find, view, compare and approve every artifact from the same dashboard. Image generation, Blender animation and paid video integration can then be added without redesigning the project core.
