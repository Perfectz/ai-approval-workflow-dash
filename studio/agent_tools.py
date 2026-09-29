"""The shared, model-independent agent interface. No director approval tool."""
from pathlib import Path
from .store import Store, WORKFLOW, Problem
from .media import inspect_media


def database():
    return Store()


def list_projects() -> list[dict]:
    """List films and their current progress. Never infer approval from a title."""
    return database().list_projects()


def get_project(project_id: str) -> dict:
    """Read direction, scenes, immutable versions, human reviews and agent tasks."""
    return database().project(project_id)


def get_next_action(project_id: str, scene_id: str | None = None) -> dict:
    """Return the next permitted stage, pinned inputs and exact director feedback."""
    return database().next_action(project_id, scene_id)


def claim_task(project_id: str, agent_name: str, scene_id: str | None = None) -> dict:
    """Claim one available stage for 15 minutes. Keep the returned token private."""
    return database().claim(project_id, agent_name, scene_id)


def heartbeat(task_id: str, token: str) -> dict:
    """Renew a live task. Changed upstream inputs invalidate the lease."""
    return database().heartbeat(task_id, token)


def register_artifact(project_id: str, payload: dict, file_paths: list[str] | None = None) -> dict:
    """Create a version against a valid task_id/task_token and pinned inputs.

    payload: title, kind, stage, scene_id, content, prompt, metadata, inputs,
    task_id, task_token. Updates also need artifact_id and expected_version.
    file_paths contains explicit absolute files produced for this project.
    Files are copied into immutable version storage; originals stay in place.
    """
    files = []
    measured = {}
    for item in file_paths or []:
        path = Path(item)
        if not path.is_absolute() or not path.is_file():
            raise Problem("Import paths must be explicit absolute files.")
        files.append((path.name, path))
        if not measured and path.suffix.lower() in (".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a"):
            measured = inspect_media(path)
    payload = {**payload, "metadata": {**payload.get("metadata", {}), **measured}}
    store = database()
    with store.db() as db:
        claim = store.required(db, "tasks", payload.get("task_id", ""))
    return store.add_version(project_id, payload, files, actor=claim["owner"], enforce_gate=True)


def validate_artifact(version_id: str) -> dict:
    """Run structural, dependency and file-integrity checks. This is not approval."""
    return database().checks(version_id)


def submit_for_review(version_id: str, task_id: str, token: str) -> dict:
    """Put the exact version into the human review queue; do not advance the gate."""
    store = database()
    record = store.get_version(version_id)
    with store.db() as db:
        claim = store._check_claim(db, task_id, token, record["project_id"])
    if record["version"].get("task_id") != task_id:
        raise Problem("This version was not produced by the claimed task.", 409)
    return store.submit(version_id, claim["owner"])


def finish_task(task_id: str, token: str, release: bool = False) -> dict:
    """Complete a submitted handoff, or release a task without a deliverable."""
    return database().finish_claim(task_id, token, release)


def save_scene(project_id: str, payload: dict, scene_id: str | None = None) -> dict:
    """Create or revise scene direction during script planning or a later stage.

    Updates require expected_revision and mark older scene artifacts stale.
    Keep package duration a whole number from 2 to 15 seconds.
    """
    store = database()
    action = store.next_action(project_id, scene_id)
    if action["stage"] in ("premise", "comic"):
        raise Problem("Approve the comic before planning video scene packages.", 409)
    return {"scene_id": store.save_scene(project_id, payload, scene_id)}


def get_workflow() -> dict:
    """Read the pinned eight-stage workflow and production constraints."""
    return WORKFLOW


def get_artifact(version_id: str) -> dict:
    """Read an exact version and absolute local file paths for its registered assets."""
    store = database()
    result = store.get_version(version_id)
    result["local_files"] = [str(store.file_path(version_id, i)[0]) for i in range(len(result["version"]["files"]))]
    return result


def prepare_generation(project_id: str, scene_id: str) -> dict:
    """Build a Wan multimodal request from approved audio, boards and previs.

    Does not upload media, submit, spend credits or retry. ready_for_api is only
    a package-format check; an agent must still verify hosted media and approval.
    """
    return database().generation_package(project_id, scene_id)


def export_project(project_id: str) -> dict:
    """Export every version, prompt, review, timeline and source file to a ZIP."""
    return {"path": str(database().export_project(project_id))}


TOOLS = {fn.__name__: fn for fn in (list_projects, get_project, get_next_action, claim_task, heartbeat, register_artifact, validate_artifact, submit_for_review, finish_task, save_scene, get_workflow, get_artifact, prepare_generation, export_project)}
