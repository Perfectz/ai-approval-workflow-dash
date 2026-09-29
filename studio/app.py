from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .bootstrap import seed
from .media import inspect_media
from .store import Store, Problem, ROOT, WORKFLOW, WORKFLOWS, workflow_for, encode, direction_hash

store = Store()
DIRECTOR_TOKEN = secrets.token_urlsafe(32)
audio_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("DIRECTOR_NO_SEED") != "1":
        seed(store)
    # An interrupted local synthesis is safe to repeat explicitly. Never infer a remote job failed.
    with store.db(True) as db:
        db.execute("UPDATE jobs SET status='interrupted' WHERE kind IN ('scratch_audio','sprite_pack') AND status IN ('queued','running')")
    yield


app = FastAPI(title="Director Studio", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Problem)
async def problem_handler(request, error):
    return JSONResponse({"detail": str(error)}, status_code=error.status)


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    host = request.url.hostname
    if host not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Director Studio is a local application."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Cross-origin requests are disabled."}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(request.headers.get("x-director-token", ""), DIRECTOR_TOKEN):
            return JSONResponse({"detail": "Refresh the studio to restore the director session."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/session")
def session():
    return {"token": DIRECTOR_TOKEN, "workflow": WORKFLOW, "workflows": list(WORKFLOWS.values()), "local_only": True, "version": "0.2.0", "provider": {"name": "Alibaba Cloud Model Studio", "model": "wan3.0-video", "mode": "package_export", "paid_submission_enabled": False}, "sprite_provider": {"name": "Google Flow", "model": "Gemini Omni Flash 1.1", "mode": "browser_ui", "api_enabled": False}}


@app.get("/api/projects")
def projects():
    return store.list_projects()


@app.post("/api/projects")
def create_project(payload: dict):
    # Sandbox bypass is only available on the imported lab, never on a user-created film.
    return store.create_project({**payload, "demo": False})


@app.get("/api/projects/{project}")
def project_detail(project: str):
    return store.project(project)


@app.patch("/api/projects/{project}")
def update_project(project: str, payload: dict):
    return store.update_project(project, payload)


@app.post("/api/projects/{project}/scenes")
def create_scene(project: str, payload: dict):
    return {"id": store.save_scene(project, payload)}


@app.patch("/api/projects/{project}/scenes/{scene}")
def update_scene(project: str, scene: str, payload: dict):
    return {"id": store.save_scene(project, payload, scene)}


@app.get("/api/projects/{project}/next")
def next_action(project: str, scene_id: str | None = None):
    return store.next_action(project, scene_id)


@app.post("/api/projects/{project}/artifacts")
async def artifact(project: str, request: Request):
    form = await request.form(max_files=30, max_part_size=200*1024*1024)
    try:
        payload = json.loads(str(form.get("payload", "{}")))
    except ValueError:
        raise Problem("Invalid artifact JSON.")
    uploads = []
    for file in form.getlist("files"):
        if not hasattr(file, "read"):
            continue
        data = await file.read(200*1024*1024 + 1)
        if len(data) > 200*1024*1024:
            raise Problem("Each file must be 200 MB or smaller.")
        uploads.append((file.filename, data))
    await form.close()
    result = await asyncio.to_thread(store.add_version, project, payload, uploads)
    version = store.get_version(result["version_id"])["version"]
    if uploads:
        for i, file in enumerate(version["files"]):
            if file["mime"].startswith(("video/", "audio/")):
                path, _ = store.file_path(result["version_id"], i)
                try:
                    measured = await asyncio.to_thread(inspect_media, path)
                    # Inspection is part of import, before this new version is exposed for review.
                    with store.db(True) as db:
                        value = json.loads(store.required(db, "versions", result["version_id"])["data"])
                        value["metadata"].update(measured)
                        import hashlib
                        value.pop("hash", None)
                        value["hash"] = hashlib.sha256(encode(value).encode()).hexdigest()
                        db.execute("UPDATE versions SET data=? WHERE id=?", (encode(value), result["version_id"]))
                except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
                    result["inspection_warning"] = str(error)
                break
    return result


@app.get("/api/versions/{version}/checks")
def checks(version: str):
    return store.checks(version)


@app.post("/api/versions/{version}/submit")
def submit(version: str):
    return store.submit(version, "director")


@app.post("/api/versions/{version}/review")
def review(version: str, payload: dict):
    return store.review(version, payload.get("decision"), payload.get("note", ""), payload.get("anchor"))


@app.get("/api/media/{version}/{index}")
def media(version: str, index: int, download: bool = False):
    path, info = store.file_path(version, index)
    inline = info["mime"].startswith(("image/", "video/", "audio/")) or info["mime"] == "application/pdf"
    return FileResponse(path, media_type=info["mime"], filename=info["name"], content_disposition_type="inline" if inline and not download else "attachment")


@app.put("/api/projects/{project}/timeline")
def timeline(project: str, payload: dict):
    if not isinstance(payload.get("expected_revision"), int):
        raise Problem("Include the project's expected_revision.")
    return store.save_timeline(project, payload.get("entries"), payload["expected_revision"])


@app.get("/api/projects/{project}/export")
def export(project: str):
    path = store.export_project(project)
    return FileResponse(path, filename=path.name, media_type="application/zip")


@app.get("/api/projects/{project}/generation/{scene}")
def generation(project: str, scene: str):
    return store.generation_package(project, scene)


@app.get("/api/audio-template")
def audio_template():
    return json.loads((ROOT / "examples/timing-demo.json").read_text(encoding="utf-8"))


def run_audio(job, project, scene_id, source, inputs, revision, direction):
    with audio_lock:
        store.update_job(job, "running", {"message": "Synthesizing temporary dialogue locally"})
        try:
            folder = store.root / "work" / job
            folder.mkdir(parents=True)
            source_path = folder / "source.json"
            source_path.write_text(encode(source), encoding="utf-8")
            process = subprocess.run([sys.executable, str(ROOT / "scripts/scratch_audio.py"), str(source_path), "--output-root", str(folder)], capture_output=True, text=True, timeout=240)
            if process.returncode not in (0, 2):
                raise ValueError(process.stderr.strip() or "Scratch audio failed.")
            result = json.loads(process.stdout)
            output = Path(result["output"])
            report = json.loads((output / "timing.json").read_text(encoding="utf-8"))
            current_project = store.project(project)
            current = next(s for s in current_project["scenes"] if s["id"] == scene_id)
            if current["revision"] != revision or direction_hash(current_project) != direction:
                raise ValueError("Scene changed during synthesis. Audio is retained in the work folder; rerun against the current direction.")
            files = [output / "mix.wav"] + sorted((output / "stems").glob("*.wav")) + [output / "timing.json", output / "dialogue.srt", output / "blender-timing.json", source_path]
            record = store.add_version(project, {"title": source["title"], "kind": "audio", "stage": "audio", "scene_id": scene_id, "inputs": inputs, "content": "\n\n".join(f"{line['character']} · {line['start']:g}s\n{line['text']}" for line in source["lines"]), "prompt": source.get("generation_prompt", ""), "metadata": {**inspect_media(output / "mix.wav"), "timing_passed": report["timing_passed"], "timing": report, "temporary_audio": True, "reference_map": "\n".join(f"{key} → {v['color']} → {v['voice']}" for key, v in source["characters"].items())}}, [(f.name, f) for f in files], actor="audio worker")
            if report["timing_passed"]:
                store.submit(record["version_id"], "audio worker")
            store.update_job(job, "completed" if report["timing_passed"] else "needs_changes", {**record, "issues": report["issues"], "duration": report["actual_duration"]})
        except Exception as error:
            store.update_job(job, "failed", {"message": str(error)[:2000]})


@app.post("/api/projects/{project}/audio")
def audio(project: str, payload: dict):
    if workflow_for(store.project(project))["id"] == "sprite-to-flow":
        raise Problem("Scratch dialogue belongs to a film project; use sprite extraction for this mode.")
    source = payload.get("source")
    if not isinstance(source, dict) or len(encode(source)) > 50000:
        raise Problem("Provide a scratch audio source under 50 KB.")
    from scripts.scratch_audio import validate
    try:
        validate(source)
    except (ValueError, KeyError, TypeError) as error:
        raise Problem(str(error))
    if any("audio_file" in line for line in source["lines"]):
        raise Problem("Use the local CLI to import existing recordings. The dashboard synthesizes plain text.")
    p = store.project(project)
    scene = next((s for s in p["scenes"] if s["id"] == payload.get("scene_id")), None)
    if not scene or source["target_duration"] != scene["duration"]:
        raise Problem("The source duration must match the selected scene package.")
    action = store.next_action(project, scene["id"])
    if not p["settings"].get("demo") and (action["stage"] not in ("audio", "boards", "blender", "wan", "edit", "complete")):
        raise Problem("Approve the screenplay before generating temporary audio.", 409)
    inputs = [a["approved_version_id"] for a in p["artifacts"] if a["stage"] in ("premise", "comic", "script") and a["approved_version_id"]]
    job = store.create_job(project, "scratch_audio", scene["id"])
    threading.Thread(target=run_audio, args=(job, project, scene["id"], source, inputs, scene["revision"], direction_hash(p)), daemon=True).start()
    return {"job_id": job, "status": "queued"}


def run_sprite_pack(job, project, scene_id, source_version_id, settings):
    store.update_job(job, "running", {"message": "Extracting and packing the approved source clip locally"})
    try:
        result = store.pack_sprite_artifact(project, scene_id, source_version_id, settings, output=store.root / "work" / job)
        store.update_job(job, "completed" if result["qc"]["passed"] else "needs_changes", result)
    except Exception as error:
        store.update_job(job, "failed", {"message": str(error)[:2000], "outputs_preserved": True})


@app.post("/api/projects/{project}/sprites")
def sprites(project: str, payload: dict):
    p = store.project(project)
    if workflow_for(p)["id"] != "sprite-to-flow":
        raise Problem("Choose a sprite project.")
    scene_id, source_id = payload.get("scene_id"), payload.get("source_version_id")
    action = store.next_action(project, scene_id)
    source = store.get_version(source_id)
    if action["stage"] != "sprite_sheet" or action["state"] != "ready" or source_id not in action["inputs"] or source["project_id"] != project:
        raise Problem("Choose a current approved Flow source clip at the sprite-sheet stage.", 409)
    if not isinstance(payload.get("settings", {}), dict) or len(encode(payload.get("settings", {}))) > 10000:
        raise Problem("Provide a small sprite settings object.")
    with store.db() as db:
        if db.execute("SELECT 1 FROM jobs WHERE project_id=? AND scene_id=? AND kind='sprite_pack' AND status IN ('queued','running')", (project, scene_id)).fetchone():
            raise Problem("Sprite extraction is already running for this animation.", 409)
    job = store.create_job(project, "sprite_pack", scene_id)
    threading.Thread(target=run_sprite_pack, args=(job, project, scene_id, source_id, payload.get("settings", {})), daemon=True).start()
    return {"job_id": job, "status": "queued"}


@app.get("/api/docs/{name}")
def document(name: str):
    files = {"spec": ROOT / "docs/WORKFLOW_SPEC.md", "agents": ROOT / "docs/AGENT_INTERFACE.md", "wan": ROOT / "docs/WAN_AND_AUDIO.md", "sprites": ROOT / "docs/SPRITE_WORKFLOW.md"}
    if name not in files or not files[name].exists():
        raise Problem("Document not found.", 404)
    return {"content": files[name].read_text(encoding="utf-8")}


if (ROOT / "dist/assets").exists():
    app.mount("/assets", StaticFiles(directory=ROOT / "dist/assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/"):
        raise Problem("API route not found.", 404)
    if path == "favicon.svg":
        return FileResponse(ROOT / "public/favicon.svg")
    index = ROOT / "dist/index.html"
    if not index.exists():
        return JSONResponse({"detail": "Run npm run build, then start the studio."}, status_code=503)
    return FileResponse(index)
