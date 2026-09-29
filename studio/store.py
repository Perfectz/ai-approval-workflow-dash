from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = json.loads((ROOT / "workflows/comic-to-wan-v1.json").read_text(encoding="utf-8"))
WORKFLOWS = {w["id"]: w for path in sorted((ROOT / "workflows").glob("*-v1.json")) for w in [json.loads(path.read_text(encoding="utf-8"))]}
STAGES = [s["id"] for s in WORKFLOW["stages"]]
KINDS = {"premise", "comic", "script", "audio", "storyboard", "reference", "previs", "video", "edit", "prompt", "notes"} | {s["kind"] for w in WORKFLOWS.values() for s in w["stages"]}
EXTENSIONS = {".png", ".gif", ".jpg", ".jpeg", ".webp", ".pdf", ".mp4", ".webm", ".mov", ".wav", ".mp3", ".m4a", ".json", ".txt", ".md", ".csv", ".srt", ".blend"}


def workflow_for(project):
    settings = project.get("settings", {})
    if isinstance(settings, str):
        settings = json.loads(settings)
    key = settings.get("workflow_id", WORKFLOW["id"])
    if key not in WORKFLOWS:
        raise Problem("This project's workflow is unavailable.", 409)
    return WORKFLOWS[key]


def stage_ids(project):
    return [s["id"] for s in workflow_for(project)["stages"]]


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def ident(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def direction_hash(project):
    value = {"brief": project["brief"], **{key: project["settings"].get(key, "") for key in ("creative_locks", "world_notes", "voice_direction")}}
    if project["settings"].get("workflow_id") == "sprite-to-flow":
        value["sprite_settings"] = project["settings"].get("sprite_settings", {})
    return hashlib.sha256(encode(value).encode()).hexdigest()


def text(value, name, limit=100000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise Problem(f"{name} must be {'non-empty ' if required else ''}text, up to {limit} characters.")
    return value.strip()


def numeric(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise Problem(f"{name} must be between {lower} and {upper}.")
    return value


class Store:
    def __init__(self, directory=None):
        self.root = Path(directory or os.environ.get("DIRECTOR_DATA", ROOT / "studio-data")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "studio.sqlite"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,title TEXT NOT NULL,brief TEXT NOT NULL,settings TEXT NOT NULL,created TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS scenes(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),ordinal INTEGER NOT NULL,data TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),scene_id TEXT REFERENCES scenes(id),kind TEXT NOT NULL,stage TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,artifact_id TEXT NOT NULL REFERENCES artifacts(id),number INTEGER NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(artifact_id,number));
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES versions(id),decision TEXT NOT NULL,note TEXT NOT NULL,anchor TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),scene_id TEXT,stage TEXT NOT NULL,owner TEXT NOT NULL,token TEXT NOT NULL,expires REAL NOT NULL,status TEXT NOT NULL,inputs TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS task_context(task_id TEXT PRIMARY KEY REFERENCES tasks(id),data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS timeline(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),version_id TEXT NOT NULL REFERENCES versions(id),ordinal INTEGER NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,kind TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,scene_id TEXT,kind TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS artifact_project ON artifacts(project_id);
            CREATE INDEX IF NOT EXISTS review_version ON reviews(version_id);
            """)

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def required(self, db, table, key):
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise Problem(f"{table.rstrip('s').capitalize()} not found.", 404)
        return dict(row)

    def event(self, db, project, kind, message, actor="director"):
        db.execute("INSERT INTO events(project_id,kind,message,actor,created) VALUES(?,?,?,?,?)", (project, kind, message, actor, now()))

    def create_project(self, payload):
        title = text(payload.get("title", ""), "Project title", 120, True)
        brief = text(payload.get("brief", ""), "Brief")
        selected = payload.get("workflow_id", WORKFLOW["id"])
        if selected not in WORKFLOWS:
            raise Problem("Choose an available workflow mode.")
        settings = {"runtime_minutes": numeric(payload.get("runtime_minutes", 2), "Runtime", .25, 240), "aspect_ratio": payload.get("aspect_ratio", "16:9"), "workflow_id": selected, "workflow_version": WORKFLOWS[selected]["version"], "budget": numeric(payload.get("budget", 0), "Budget", 0, 100000), "demo": bool(payload.get("demo", False))}
        if selected == "sprite-to-flow":
            settings["sprite_settings"] = {"view": "side", "pixel_art": True, "cell_width": 128, "cell_height": 128, "sprite_fps": 12, "background_key": "#FF00FF"}
            settings["target_engine"] = text(payload.get("target_engine", "Godot"), "Target engine", 120, True)
            for field in ("cell_width", "cell_height"):
                size = numeric(payload.get(field, 128), field, 16, 1024)
                if int(size) != size:
                    raise Problem("Sprite cell dimensions must be whole numbers.")
                settings["sprite_settings"][field] = size
        if settings["aspect_ratio"] not in ("16:9", "9:16", "1:1"):
            raise Problem("Choose a supported aspect ratio.")
        if selected == "sprite-to-flow" and settings["aspect_ratio"] == "1:1":
            raise Problem("Flow Omni source clips use landscape or portrait; sprite cells may still be square.")
        key = ident("project")
        with self.db(True) as db:
            db.execute("INSERT INTO projects(id,title,brief,settings,created) VALUES(?,?,?,?,?)", (key, title, brief, encode(settings), now()))
            self.event(db, key, "project", f"Created {title}")
        return self.project(key)

    def list_projects(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM projects ORDER BY created DESC")]
        result = []
        for key in ids:
            project = self.project(key)
            result.append({k: project[k] for k in ("id", "title", "brief", "settings", "created", "revision", "stage_status", "review_count", "artifact_count", "scene_count")})
        return result

    def update_project(self, key, payload):
        with self.db(True) as db:
            p = self.required(db, "projects", key)
            if payload.get("expected_revision") != p["revision"]:
                raise Problem("This project changed. Refresh before saving.", 409)
            settings = json.loads(p["settings"])
            for field in ("creative_locks", "voice_direction", "delivery_notes", "world_notes"):
                if field in payload:
                    settings[field] = text(payload[field], field)
            if "budget" in payload:
                settings["budget"] = numeric(payload["budget"], "Budget", 0, 100000)
            if "workflow_id" in payload and payload["workflow_id"] != settings.get("workflow_id", WORKFLOW["id"]):
                raise Problem("Create a new project to change workflow mode.")
            if "sprite_settings" in payload:
                if settings.get("workflow_id") != "sprite-to-flow" or not isinstance(payload["sprite_settings"], dict) or len(encode(payload["sprite_settings"])) > 10000:
                    raise Problem("Sprite settings must be a small object on a sprite project.")
                settings["sprite_settings"] = payload["sprite_settings"]
            db.execute("UPDATE projects SET title=?,brief=?,settings=?,revision=revision+1 WHERE id=?", (text(payload.get("title", p["title"]), "Title", 120, True), text(payload.get("brief", p["brief"]), "Brief"), encode(settings), key))
            self.event(db, key, "direction", "Updated project direction")
        return self.project(key)

    def save_scene(self, project, payload, key=None):
        with self.db(True) as db:
            project_record = self.required(db, "projects", project)
            old = self.required(db, "scenes", key) if key else None
            if old and (old["project_id"] != project or payload.get("expected_revision") != old["revision"]):
                raise Problem("Scene changed or belongs to another project.", 409)
            value = json.loads(old["data"]) if old else {}
            for field in ("title", "purpose", "emotion", "start_state", "end_state", "locked", "flexible", "voice_notes"):
                value[field] = text(payload.get(field, value.get(field, "")), field, 120 if field == "title" else 10000, field == "title")
            sprite = workflow_for(project_record)["id"] == "sprite-to-flow"
            value["duration"] = numeric(payload.get("duration", value.get("duration", 8 if sprite else 15)), "Package duration", 2, 15)
            if int(value["duration"]) != value["duration"]:
                raise Problem("Generation package duration must be a whole number of seconds.")
            if sprite:
                project_defaults = json.loads(project_record["settings"]).get("sprite_settings", {})
                if value["duration"] not in (4, 6, 8, 10):
                    raise Problem("Omni source clips use 4, 6, 8 or 10 seconds.")
                for field, default in (("action", "idle"), ("direction", "right"), ("background_key", "#FF00FF")):
                    value[field] = text(payload.get(field, value.get(field, default)), field, 120, True)
                for field, default, low, high in (("frame_count", 8, 2, 128), ("cell_width", 128, 16, 1024), ("cell_height", 128, 16, 1024), ("columns", 4, 1, 32), ("sprite_fps", 12, 1, 60), ("key_tolerance", 24, 0, 255)):
                    value[field] = numeric(payload.get(field, value.get(field, project_defaults.get(field, default))), field, low, high)
                    if int(value[field]) != value[field]:
                        raise Problem(f"{field} must be a whole number.")
                value["sample_start"] = numeric(payload.get("sample_start", value.get("sample_start", 0)), "Sampling start", 0, value["duration"])
                value["sample_end"] = numeric(payload.get("sample_end", value.get("sample_end", min(1, value["duration"]))), "Sampling end", 0, value["duration"])
                if value["sample_end"] <= value["sample_start"]:
                    raise Problem("Sampling end must follow sampling start.")
                value["pixel_art"] = bool(payload.get("pixel_art", value.get("pixel_art", True)))
                value["loop"] = bool(payload.get("loop", value.get("loop", value["action"] in ("idle", "walk", "run", "hover"))))
                value["padding"] = numeric(payload.get("padding", value.get("padding", 2)), "Cell padding", 0, min(value["cell_width"], value["cell_height"]) // 4)
                if int(value["padding"]) != value["padding"]:
                    raise Problem("Cell padding must be a whole number of pixels.")
                pivot = payload.get("feet_pivot", value.get("feet_pivot", [.5, 1]))
                if not isinstance(pivot, list) or len(pivot) != 2:
                    raise Problem("Feet pivot must be two normalized coordinates.")
                value["feet_pivot"] = [numeric(x, "Feet pivot", 0, 1) for x in pivot]
                if value["columns"] > value["frame_count"]:
                    raise Problem("Grid columns cannot exceed the frame count.")
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", value["background_key"]):
                    raise Problem("Choose a background key in #RRGGBB format.")
            if old:
                db.execute("UPDATE scenes SET data=?,revision=revision+1 WHERE id=?", (encode(value), key))
            else:
                key = ident("scene")
                ordinal = db.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM scenes WHERE project_id=?", (project,)).fetchone()[0]
                db.execute("INSERT INTO scenes(id,project_id,ordinal,data) VALUES(?,?,?,?)", (key, project, ordinal, encode(value)))
            self.event(db, project, "scene", f"{'Updated' if old else 'Created'} {value['title']}")
        return key

    def project(self, key):
        with self.db() as db:
            return self._project(db, key)

    def _project(self, db, key):
        p = self.required(db, "projects", key)
        p["settings"] = json.loads(p["settings"])
        p["workflow"] = workflow_for(p)
        p["workflow_id"] = p["workflow"]["id"]
        p["scenes"] = [{**dict(r), **json.loads(r["data"])} for r in db.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY ordinal", (key,))]
        p["artifacts"] = [dict(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? ORDER BY created", (key,))]
        versions, approved = {}, {}
        for artifact in p["artifacts"]:
            artifact["versions"] = []
            for row in db.execute("SELECT * FROM versions WHERE artifact_id=? ORDER BY number DESC", (artifact["id"],)):
                v = {**dict(row), **json.loads(row["data"])}
                v.pop("data", None)
                v["reviews"] = [{**dict(r), "anchor": json.loads(r["anchor"])} for r in db.execute("SELECT * FROM reviews WHERE version_id=? ORDER BY rowid DESC", (v["id"],))]
                decision = next((r["decision"] for r in v["reviews"] if r["decision"] != "comment"), None)
                v["status"] = decision or ("in_review" if v.get("submitted") else "draft")
                v["artifact_id"] = artifact["id"]
                versions[v["id"]] = v
                if decision == "approved" and artifact["id"] not in approved:
                    approved[artifact["id"]] = v["id"]
                artifact["versions"].append(v)
        def stale(version_id, trail=None):
            trail = set(trail or ())
            if version_id in trail:
                return True
            trail.add(version_id)
            v = versions.get(version_id)
            if not v:
                return True
            if v.get("direction_hash") and v["direction_hash"] != direction_hash(p):
                return True
            for source in v.get("inputs", []):
                dep = versions.get(source)
                if not dep or approved.get(dep["artifact_id"]) != source or stale(source, trail):
                    return True
            scene_id = v.get("scene_id")
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            if scene and v.get("scene_revision") and scene["revision"] != v["scene_revision"]:
                return True
            return False
        for v in versions.values():
            v["stale"] = stale(v["id"])
            v["effective_status"] = "needs_update" if v["stale"] else v["status"]
        for a in p["artifacts"]:
            a["latest"] = a["versions"][0] if a["versions"] else None
            a["approved_version_id"] = approved.get(a["id"])
        stage_status = []
        for stage in p["workflow"]["stages"]:
            relevant = [a for a in p["artifacts"] if a["stage"] == stage["id"] and a["kind"] == stage["kind"]]
            good = [a for a in relevant if a["approved_version_id"] and not versions[a["approved_version_id"]]["stale"]]
            if stage["scope"] == "scene":
                complete = bool(p["scenes"]) and all(any(a["scene_id"] == s["id"] for a in good) for s in p["scenes"])
            else:
                complete = bool(good)
            stage_status.append({**stage, "complete": complete, "count": len(relevant), "approved_count": len(good)})
        p["stage_status"] = stage_status
        p["review_count"] = sum(1 for a in p["artifacts"] if a["latest"] and a["latest"]["effective_status"] == "in_review")
        p["artifact_count"], p["scene_count"] = len(p["artifacts"]), len(p["scenes"])
        p["events"] = [dict(r) for r in db.execute("SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 100", (key,))]
        p["tasks"] = [dict(r) for r in db.execute("SELECT id,project_id,scene_id,stage,owner,expires,status,created FROM tasks WHERE project_id=? ORDER BY created DESC", (key,))]
        p["jobs"] = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC", (key,))]
        p["timeline"] = [{**dict(r), **json.loads(r["data"]), "version": versions.get(r["version_id"])} for r in db.execute("SELECT * FROM timeline WHERE project_id=? ORDER BY ordinal", (key,))]
        return p

    def next_action(self, project, scene_id=None):
        p = self.project(project)
        return self._next(p, scene_id)

    def _next(self, p, scene_id=None):
        stages = stage_ids(p)
        if scene_id and not any(s["id"] == scene_id for s in p["scenes"]):
            raise Problem("Scene does not belong to this project.")
        for stage in p["stage_status"]:
            items = [a for a in p["artifacts"] if a["stage"] == stage["id"] and a["kind"] == stage["kind"] and (not scene_id or stage["scope"] == "project" or a["scene_id"] == scene_id)]
            if scene_id and stage["scope"] == "scene":
                complete = any(a["approved_version_id"] and not next(v for v in a["versions"] if v["id"] == a["approved_version_id"])["stale"] for a in items)
            else:
                complete = stage["complete"]
            if complete:
                continue
            waiting = [a for a in items if a["latest"] and a["latest"]["effective_status"] == "in_review"]
            inputs = [a["approved_version_id"] for a in p["artifacts"] if a["approved_version_id"] and stages.index(a["stage"]) < stages.index(stage["id"]) and (not scene_id or not a["scene_id"] or a["scene_id"] == scene_id) and not next(v for v in a["versions"] if v["id"] == a["approved_version_id"])["stale"]]
            return {"stage": stage["id"], "name": stage["name"], "state": "awaiting_review" if waiting else "ready", "instruction": stage["instruction"], "deliverable": stage["deliverable"], "checks": stage["checks"], "inputs": inputs, "scene_id": scene_id, "needs_scene": stage["scope"] == "scene" and not scene_id, "feedback": [r for a in items for v in a["versions"][:1] for r in v["reviews"]], "review_versions": [a["latest"]["id"] for a in waiting]}
        return {"stage": "complete", "name": "Complete", "state": "complete", "inputs": [], "instruction": "All required stages have approved artifacts."}

    def add_version(self, project, payload, uploaded=None, actor="director", enforce_gate=False):
        kind = payload.get("kind", "notes")
        selected_workflow = workflow_for(self.project(project))
        stage = payload.get("stage", selected_workflow["stages"][0]["id"])
        allowed_kinds = {s["kind"] for s in selected_workflow["stages"]} | {"notes", "reference", "prompt"}
        if kind not in allowed_kinds or stage not in [s["id"] for s in selected_workflow["stages"]]:
            raise Problem("Unknown artifact kind or stage for this workflow mode.")
        title = text(payload.get("title", ""), "Artifact title", 160, True)
        content = text(payload.get("content", ""), "Artifact text")
        prompt = text(payload.get("prompt", ""), "Generation prompt", 20000)
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict) or len(encode(metadata)) > 100000:
            raise Problem("Metadata must be a JSON object smaller than 100 KB.")
        inputs = payload.get("inputs", [])
        if not isinstance(inputs, list) or len(inputs) > 100 or any(not isinstance(x, str) for x in inputs):
            raise Problem("Inputs must be a list of version IDs.")
        version_id = ident("version")
        with self.db(True) as db:
            p = self._project(db, project)
            scene_id = payload.get("scene_id") or None
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            if scene_id and not scene:
                raise Problem("Scene belongs to another project.")
            artifact_id = payload.get("artifact_id")
            previous = None
            if artifact_id:
                artifact = self.required(db, "artifacts", artifact_id)
                if artifact["project_id"] != project:
                    raise Problem("Artifact belongs to another project.")
                previous = db.execute("SELECT * FROM versions WHERE artifact_id=? ORDER BY number DESC LIMIT 1", (artifact_id,)).fetchone()
                if not previous or payload.get("expected_version") != previous["id"]:
                    raise Problem("A newer version exists. Refresh before saving your changes.", 409)
                kind, stage, scene_id = artifact["kind"], artifact["stage"], artifact["scene_id"]
                title = artifact["title"]
                scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            else:
                artifact_id = ident("artifact")
                db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)", (artifact_id, project, scene_id, kind, stage, title, now()))
            if enforce_gate:
                eligible = self._next(p, scene_id)
                if eligible["stage"] != stage or eligible["state"] != "ready":
                    raise Problem(f"The next permitted action is {eligible['name']} ({eligible['state']}).", 409)
                if eligible.get("needs_scene"):
                    raise Problem("Select a scene package for this stage.")
                if set(eligible["inputs"]) - set(inputs):
                    raise Problem("Include the pinned approved inputs from get_next_action.", 409)
                if not payload.get("task_id"):
                    raise Problem("Claim the task before registering agent work.", 409)
            if payload.get("task_id"):
                claim = self._check_claim(db, payload["task_id"], payload.get("task_token"), project)
                if claim["stage"] != stage or claim["scene_id"] != scene_id:
                    raise Problem("The artifact must match the claimed stage and scene.", 409)
            for source in inputs:
                dep = db.execute("SELECT a.project_id,a.id FROM versions v JOIN artifacts a ON a.id=v.artifact_id WHERE v.id=?", (source,)).fetchone()
                if not dep or dep["project_id"] != project or dep["id"] == artifact_id:
                    raise Problem("Input versions must belong to this project and another artifact.")
            files = []
            if previous and payload.get("inherit_files", True):
                files = json.loads(previous["data"]).get("files", [])
            if uploaded:
                files = []
                folder = self.root / "assets" / version_id
                folder.mkdir(parents=True, exist_ok=False)
                for index, item in enumerate(uploaded):
                    filename, source = item
                    suffix = Path(filename).suffix.lower()
                    if suffix not in EXTENSIONS:
                        raise Problem(f"Unsupported file type: {suffix or filename}")
                    safe_name = f"{index:02d}_" + "".join(c for c in Path(filename).name if c.isalnum() or c in " ._-()")[:160]
                    dest = folder / safe_name
                    if isinstance(source, bytes):
                        dest.write_bytes(source)
                    else:
                        shutil.copyfile(source, dest)
                    size = dest.stat().st_size
                    if size > 200 * 1024 * 1024:
                        raise Problem("Each file must be 200 MB or smaller.")
                    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    if suffix in (".md", ".srt", ".csv", ".txt"):
                        mime = "text/plain"
                    files.append({"name": Path(filename).name, "path": dest.relative_to(self.root).as_posix(), "mime": mime, "size": size, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
            if not (files or content or prompt):
                raise Problem("Add a file, script, notes or prompt before saving.")
            version = {"content": content, "prompt": prompt, "metadata": metadata, "inputs": list(dict.fromkeys(inputs)), "files": files, "author": actor, "submitted": False, "scene_id": scene_id, "scene_revision": scene["revision"] if scene else None, "direction_hash": direction_hash(p), "task_id": payload.get("task_id")}
            version["hash"] = hashlib.sha256(encode(version).encode()).hexdigest()
            number = previous["number"] + 1 if previous else 1
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (version_id, artifact_id, number, encode(version), now()))
            self.event(db, project, "artifact", f"Saved {title} v{number}", actor)
        return {"artifact_id": artifact_id, "version_id": version_id, "number": number}

    def get_version(self, version_id):
        with self.db() as db:
            v = self.required(db, "versions", version_id)
            a = self.required(db, "artifacts", v["artifact_id"])
        p = self.project(a["project_id"])
        artifact = next(x for x in p["artifacts"] if x["id"] == a["id"])
        return {"project_id": a["project_id"], "artifact": {k: v for k, v in artifact.items() if k not in ("versions", "latest")}, "version": next(v for v in artifact["versions"] if v["id"] == version_id)}

    def file_path(self, version_id, index):
        record = self.get_version(version_id)
        files = record["version"]["files"]
        if not isinstance(index, int) or not 0 <= index < len(files):
            raise Problem("File not found.", 404)
        info = files[index]
        path = (self.root / info["path"]).resolve()
        if not path.is_relative_to(self.root / "assets") or not path.is_file():
            raise Problem("Registered file is missing.", 404)
        return path, info

    def checks(self, version_id):
        record = self.get_version(version_id)
        v, a = record["version"], record["artifact"]
        issues, passed = [], []
        p = self.project(record["project_id"])
        stages = stage_ids(p)
        stage = next(s for s in workflow_for(p)["stages"] if s["id"] == a["stage"])
        if a["kind"] == stage["kind"]:
            if stage["scope"] == "scene" and not a["scene_id"]:
                issues.append("This stage needs a scene package.")
            if stage["scope"] == "project" and a["scene_id"]:
                issues.append("This deliverable must be scoped to the whole project.")
            if not p["settings"].get("demo"):
                required = [x["approved_version_id"] for x in p["artifacts"] if x["approved_version_id"] and stages.index(x["stage"]) < stages.index(a["stage"]) and (not a["scene_id"] or not x["scene_id"] or x["scene_id"] == a["scene_id"])]
                if set(required) - set(v["inputs"]):
                    issues.append("Pin the current approved upstream versions before requesting approval.")
        if v["stale"]:
            issues.append("Approved inputs or scene direction changed. Create a reviewed replacement version.")
        for index, file in enumerate(v["files"]):
            path, _ = self.file_path(version_id, index)
            if hashlib.sha256(path.read_bytes()).hexdigest() != file["sha256"]:
                issues.append(f"File integrity changed: {file['name']}")
        if v["files"]:
            passed.append("Registered file hashes verified")
        images = [f for f in v["files"] if f["mime"].startswith("image/")]
        media = [f for f in v["files"] if f["mime"].startswith(("video/", "audio/"))]
        if p["workflow_id"] == "sprite-to-flow":
            self.sprite_checks(p, a, v, images, media, issues, passed)
        if a["kind"] == "comic" and len(images) != 10:
            issues.append("The comic package needs exactly 10 page images.")
        if a["kind"] == "storyboard" and not images:
            issues.append("Add the storyboard images.")
        if a["kind"] == "storyboard" and not v["metadata"].get("reference_map"):
            issues.append("Explain character IDs and the ordered reference mapping in metadata.reference_map.")
        if a["kind"] in ("audio", "previs", "video", "edit") and not media:
            issues.append("Add playable media to this package.")
        if a["kind"] in ("previs", "video", "edit") and not any(f["mime"].startswith("video/") for f in media):
            issues.append("This stage requires a playable video.")
        if a["kind"] == "previs" and not any(f["name"].lower().endswith(".blend") for f in v["files"]):
            issues.append("Attach the editable Blender scene (.blend).")
        if a["kind"] in ("premise", "script") and not v["content"]:
            issues.append("Add the readable story or script text.")
        timing = v["metadata"].get("timing_passed")
        if a["kind"] == "audio" and timing is False:
            issues.append("Audio timing check failed.")
        if a["kind"] == "audio" and timing is not True:
            issues.append("Include a passing timing report (metadata.timing_passed).")
        if timing is True:
            passed.append("Audio tool reported passing timing checks")
        if a["kind"] in ("video", "previs", "audio") and not v["metadata"].get("duration"):
            issues.append("Record the measured media duration in metadata.duration.")
        if v["metadata"].get("duration"):
            numeric(v["metadata"]["duration"], "Measured duration", .001, 86400)
        if media and a["kind"] in ("audio", "previs", "video", "edit"):
            from .media import inspect_media
            index = next(i for i, f in enumerate(v["files"]) if f["mime"].startswith(("audio/", "video/")))
            try:
                measured = inspect_media(self.file_path(version_id, index)[0])
                actual = measured.get("duration")
                if not actual:
                    issues.append("Media duration could not be measured; install ffprobe for video imports.")
                elif abs(actual - v["metadata"].get("duration", actual)) > 1/30:
                    issues.append("Recorded duration does not match the media file.")
                scene = next((s for s in p["scenes"] if s["id"] == a["scene_id"]), None)
                if actual and scene and a["kind"] in ("audio", "previs", "video") and abs(actual-scene["duration"]) > 1/30:
                    issues.append("Media duration does not match the scene package.")
            except (ValueError, OSError, KeyError) as error:
                issues.append(f"Could not inspect media: {error}")
        if not issues:
            passed.append("Artifact structure is ready for human review")
        return {"passed": not issues, "checks": passed, "issues": issues, "human_review_required": True}

    def sprite_checks(self, project, artifact, version, images, media, issues, passed):
        kind, metadata = artifact["kind"], version["metadata"]
        if kind in ("sprite_brief", "sprite_motion", "sprite_delivery") and not version["content"]:
            issues.append("Add a readable sprite brief, motion plan or delivery manifest.")
        if kind in ("sprite_design", "sprite_board") and not images:
            issues.append("Attach the character/reference or action-board images.")
        if kind == "sprite_board":
            if not version["prompt"] or not metadata.get("reference_map"):
                issues.append("Include the exact Flow prompt and clean-reference mapping.")
            if not isinstance(metadata.get("flow_references"), list) or not metadata["flow_references"]:
                issues.append("Choose clean Flow references in metadata.flow_references.")
        if kind == "sprite_video":
            videos = [f for f in version["files"] if f["mime"].startswith("video/")]
            if not videos:
                issues.append("Attach the original clip downloaded from Google Flow.")
            receipt = metadata.get("flow", {})
            if not isinstance(receipt, dict) or receipt.get("provider") != "Google Flow" or receipt.get("execution") != "browser_ui" or not receipt.get("selected_model") or not receipt.get("evidence"):
                issues.append("Record the visible Flow model, browser execution and generation evidence in metadata.flow.")
            attempt = receipt.get("attempt_id") if isinstance(receipt, dict) else None
            with self.db() as db:
                row = db.execute("SELECT * FROM jobs WHERE id=? AND project_id=? AND kind='flow_generation'", (attempt, project["id"])).fetchone()
            if not row or row["scene_id"] != artifact["scene_id"]:
                issues.append("Link this clip to its reserved Flow attempt.")
            else:
                data = json.loads(row["data"])
                if data.get("board_version_id") not in version["inputs"]:
                    issues.append("Pin the board version used by this Flow attempt.")
                if row["status"] not in ("downloaded",):
                    issues.append("Record the Flow attempt as downloaded before reviewing its clip.")
                if receipt.get("selected_model") != data.get("selected_model"):
                    issues.append("The imported model receipt must match the model reserved for this attempt.")
                settings = receipt.get("settings", {})
                scene = next((s for s in project["scenes"] if s["id"] == artifact["scene_id"]), None)
                if not isinstance(settings, dict) or not scene or settings.get("duration") != scene["duration"] or settings.get("aspect_ratio") != project["settings"]["aspect_ratio"] or settings.get("outputs") != 1:
                    issues.append("Record the approved duration, aspect ratio and one output in metadata.flow.settings.")
            if videos:
                from .media import inspect_media
                try:
                    index = next(i for i, f in enumerate(version["files"]) if f["mime"].startswith("video/"))
                    measured = inspect_media(self.file_path(version["id"], index)[0])
                    scene = next((s for s in project["scenes"] if s["id"] == artifact["scene_id"]), None)
                    if not measured.get("duration"):
                        issues.append("Install ffprobe to measure the imported Flow clip.")
                    elif scene and abs(measured["duration"] - scene["duration"]) > .15:
                        issues.append("The source clip duration does not match the approved Omni plan.")
                except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
                    issues.append(f"Could not measure the sprite source clip: {error}")
        if kind == "sprite_sheet":
            sprite = metadata.get("sprite", {})
            if not isinstance(sprite, dict):
                issues.append("Sprite metadata must be an object.")
                return
            sheet_index = sprite.get("sheet_file_index", 0)
            atlas_index = sprite.get("atlas_file_index", 2)
            try:
                from PIL import Image
                sheet_path, sheet_info = self.file_path(version["id"], sheet_index)
                atlas_path, _ = self.file_path(version["id"], atlas_index)
                atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
                if not isinstance(atlas, dict) or not isinstance(atlas.get("frames"), list) or any(not isinstance(frame, dict) for frame in atlas["frames"]):
                    raise ValueError("Atlas frames must be a list of frame objects.")
                with Image.open(sheet_path) as sheet:
                    if sheet.format != "PNG" or sheet.mode != "RGBA":
                        issues.append("The sprite sheet must be an RGBA PNG with transparency.")
                    if not atlas.get("frames"):
                        issues.append("The sprite atlas must contain frame rectangles.")
                    scene = next((s for s in project["scenes"] if s["id"] == artifact["scene_id"]), None)
                    if scene and len(atlas.get("frames", [])) != scene["frame_count"]:
                        issues.append("Frame count differs from the approved animation plan.")
                    if sheet.mode == "RGBA" and (sheet.getextrema()[3][0] != 0 or sheet.getextrema()[3][1] == 0):
                        issues.append("The sheet needs both visible pixels and transparent background.")
                    if scene:
                        rows = math.ceil(scene["frame_count"] / scene["columns"])
                        if sheet.size != (scene["columns"] * scene["cell_width"], rows * scene["cell_height"]):
                            issues.append("Sheet dimensions differ from the approved grid and cells.")
                        for frame in atlas.get("frames", []):
                            rect = frame.get("rect", frame.get("frame", {}))
                            pivot = frame.get("pivot", {})
                            if not isinstance(rect, dict) or any(isinstance(rect.get(k), bool) or not isinstance(rect.get(k), (int, float)) or not math.isfinite(rect[k]) for k in ("x", "y", "w", "h")):
                                issues.append("Atlas frames need numeric rectangles.")
                                break
                            if rect["x"] < 0 or rect["y"] < 0 or rect["w"] != scene["cell_width"] or rect["h"] != scene["cell_height"] or rect["x"] + rect["w"] > sheet.width or rect["y"] + rect["h"] > sheet.height:
                                issues.append("An atlas rectangle lies outside the sheet or differs from its cell size.")
                                break
                            if not isinstance(pivot, dict) or any(not isinstance(pivot.get(k), (int, float)) or not math.isfinite(pivot[k]) for k in ("x", "y")) or not 0 <= pivot["x"] <= rect["w"] or not 0 <= pivot["y"] <= rect["h"]:
                                issues.append("Record valid per-frame pivots inside each cell.")
                                break
                            duration = frame.get("duration_ms")
                            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or abs(duration - 1000 / scene["sprite_fps"]) > 1:
                                issues.append("Atlas playback timing differs from the approved sprite FPS.")
                                break
                qc = metadata.get("sprite", {}).get("qc", {})
                if not isinstance(qc, dict) or qc.get("passed") is not True:
                    issues.append("Include passing local sprite-processing QC.")
                passed.append("Sprite sheet and atlas decoded locally")
            except (Problem, ValueError, OSError, KeyError, TypeError) as error:
                issues.append(f"Sprite sheet or atlas is invalid: {error}")
        if kind == "sprite_preview":
            if not any(f["mime"].startswith(("video/", "image/gif")) for f in version["files"]):
                issues.append("Attach an animated in-game preview (video or GIF).")
            if not metadata.get("engine_notes"):
                issues.append("Record the engine, scale, pivot and tested animation states.")

    def flow_package(self, project, scene_id):
        p = self.project(project)
        if workflow_for(p)["id"] != "sprite-to-flow":
            raise Problem("This project does not use the sprite workflow.")
        scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
        if not scene:
            raise Problem("Select an animation entry.")
        boards = [a for a in p["artifacts"] if a["kind"] == "sprite_board" and a["scene_id"] == scene_id and a["approved_version_id"]]
        board = next((v for a in reversed(boards) for v in a["versions"] if v["id"] == a["approved_version_id"] and not v["stale"]), None)
        if not board:
            raise Problem("Approve the current action boards and Flow prompt first.", 409)
        references, issues = [], []
        for ref in board["metadata"].get("flow_references", []):
            if not isinstance(ref, dict) or ref.get("role") not in ("ingredient", "first_frame", "last_frame"):
                raise Problem("Flow references need an ingredient, first_frame or last_frame role.")
            source_id = board["id"] if ref.get("version_id") == "self" else ref.get("version_id")
            record = self.get_version(source_id)
            source = record["version"]
            if record["project_id"] != project or source["stale"] or record["artifact"]["approved_version_id"] != source_id or (source_id != board["id"] and source_id not in board["inputs"]):
                raise Problem("Flow references must be current approved images pinned by this board.", 409)
            path, info = self.file_path(source_id, ref.get("file_index"))
            if hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
                raise Problem("A pinned Flow reference changed on disk. Restore or review a replacement before uploading.", 409)
            if not info["mime"].startswith("image/") or info["mime"] == "image/gif":
                raise Problem("Choose a clean still image for Flow references.")
            references.append({"version_id": source_id, "file_index": ref["file_index"], "role": ref["role"], "name": info["name"], "sha256": info["sha256"], "local_path": str(path)})
        if not references:
            issues.append("Choose clean approved image references.")
        if any(r["role"] == "ingredient" for r in references) and any(r["role"] != "ingredient" for r in references):
            issues.append("Choose ingredients or first/last frames as one Flow input mode.")
        if sum(r["role"] == "first_frame" for r in references) > 1 or sum(r["role"] == "last_frame" for r in references) > 1:
            issues.append("Use only one first frame and one last frame.")
        if any(r["role"] == "last_frame" for r in references) and not any(r["role"] == "first_frame" for r in references):
            issues.append("A last frame requires a first frame.")
        allowance = board["metadata"].get("flow_allowance", {})
        valid_allowance = isinstance(allowance, dict) and isinstance(allowance.get("max_generations"), int) and not isinstance(allowance.get("max_generations"), bool) and 1 <= allowance["max_generations"] <= 100 and isinstance(allowance.get("max_credits"), (float, int)) and not isinstance(allowance.get("max_credits"), bool) and math.isfinite(allowance["max_credits"]) and 0 <= allowance["max_credits"] <= 100000 and allowance.get("outputs_per_generation") == 1 and allowance.get("upload_authorized") is True
        if not valid_allowance:
            issues.append("Approve an explicit generation/credit allowance and reference upload permission with this exact board version.")
        with self.db() as db:
            attempts = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM jobs WHERE project_id=? AND scene_id=? AND kind='flow_generation'", (project, scene_id))]
        relevant = [a for a in attempts if a["data"].get("board_version_id") == board["id"]]
        if any(a["status"] in ("reserved", "submitted", "unknown") for a in attempts):
            issues.append("An existing Flow attempt is unresolved. Inspect it before considering another generation.")
        if valid_allowance and len(relevant) >= allowance["max_generations"]:
            issues.append("This board's generation allowance is exhausted. Review a new allowance before another attempt.")
        return {"mode": "browser_ui", "provider": "Google Flow", "model": "Gemini Omni Flash 1.1", "requested_model": "Google Omni", "ui": {"url": "https://labs.google/fx/tools/flow"}, "input": {"prompt": board["prompt"]}, "references": references, "parameters": {"duration": scene["duration"], "aspect_ratio": p["settings"]["aspect_ratio"], "outputs": 1}, "allowance": allowance, "issues": issues, "ready_for_browser": not issues, "ready_for_api": False, "provenance": {"project_id": project, "scene_id": scene_id, "board_version_id": board["id"], "versions": board["inputs"], "direction_hash": direction_hash(p), "scene_revision": scene["revision"]}, "submission": "Browser handoff only. No upload, generation click or API request has been made.", "instructions": ["Inspect the live Flow model and controls; record the exact visible label.", "Use only the approved clean references and exact prompt.", "Reserve one observed credit cost locally immediately before Generate.", "After an uncertain result, inspect the existing generation; never silently retry.", "Download the original clip and retain UI evidence for director review."]}

    def reserve_flow_attempt(self, project, scene_id, task_id, token, selected_model, credit_cost):
        package = self.flow_package(project, scene_id)
        if not package["ready_for_browser"]:
            raise Problem(" ".join(package["issues"]), 409)
        selected_model = text(selected_model, "Visible Flow model", 120, True)
        if "omni" not in selected_model.lower():
            raise Problem("Select the approved Omni model in Flow; request changes before substituting another model.")
        cost = numeric(credit_cost, "Observed Flow credit cost", 0, 100000)
        with self.db(True) as db:
            claim = self._check_claim(db, task_id, token, project)
            if claim["stage"] != "sprite_flow" or claim["scene_id"] != scene_id:
                raise Problem("Claim the Flow generation stage for this animation first.", 409)
            current = self._project(db, project)
            if direction_hash(current) != package["provenance"]["direction_hash"]:
                raise Problem("Project direction changed. Rebuild the Flow package.", 409)
            board_id = package["provenance"]["board_version_id"]
            if board_id not in json.loads(claim["inputs"]):
                raise Problem("The Flow board changed. Claim its current version.", 409)
            attempts = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM jobs WHERE project_id=? AND scene_id=? AND kind='flow_generation'", (project, scene_id))]
            if any(a["status"] in ("reserved", "submitted", "unknown") for a in attempts):
                raise Problem("An existing Flow attempt is unresolved. Inspect it before considering another generation.", 409)
            relevant = [a for a in attempts if a["data"].get("board_version_id") == board_id]
            if len(relevant) >= package["allowance"]["max_generations"] or sum(a["data"]["reserved_credits"] for a in relevant) + cost > package["allowance"]["max_credits"]:
                raise Problem("The approved generation or credit allowance is exhausted.", 409)
            key = ident("job")
            data = {"board_version_id": board_id, "task_id": task_id, "selected_model": selected_model, "reserved_credits": cost, "output_count": 1, "prompt": package["input"]["prompt"], "reference_versions": package["references"], "message": "Reserved for one browser Generate click; no external action performed"}
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (key, project, scene_id, "flow_generation", "reserved", encode(data), now(), now()))
            self.event(db, project, "flow", f"Reserved one Flow attempt ({cost:g} credit cap)", claim["owner"])
        return {"attempt_id": key, "status": "reserved", "reserved_credits": cost, "no_external_action": True}

    def record_flow_result(self, attempt_id, task_id, token, status, evidence, project_url=""):
        if status not in ("submitted", "downloaded", "failed", "unknown"):
            raise Problem("Choose submitted, downloaded, failed or unknown.")
        evidence = text(evidence, "Flow UI evidence", 10000, True)
        project_url = text(project_url, "Flow project URL", 2000)
        if project_url:
            from urllib.parse import urlparse
            url = urlparse(project_url)
            if url.scheme != "https" or url.hostname != "labs.google" or url.username or url.password:
                raise Problem("Use the visible HTTPS labs.google Flow project URL.")
        with self.db(True) as db:
            row = self.required(db, "jobs", attempt_id)
            data = json.loads(row["data"])
            claim = self._check_claim(db, task_id, token, row["project_id"])
            if row["kind"] != "flow_generation" or claim["scene_id"] != row["scene_id"]:
                raise Problem("The Flow result does not belong to this claimed task.", 409)
            if row["status"] in ("downloaded", "failed"):
                raise Problem("This attempt is already closed; preserve its receipt.", 409)
            data.setdefault("history", []).append({"status": status, "evidence": evidence, "task_id": task_id, "owner": claim["owner"], "at": now()})
            if data.get("task_id") != task_id:
                data["reconciled_by_task_id"] = task_id
            data.update({"evidence": evidence, "project_url": project_url, "message": f"Browser result recorded: {status}"})
            db.execute("UPDATE jobs SET status=?,data=?,updated=? WHERE id=?", (status, encode(data), now(), attempt_id))
            self.event(db, row["project_id"], "flow", f"Recorded Flow attempt: {status}", claim["owner"])
        return {"attempt_id": attempt_id, "status": status, "no_external_action": True}

    def pack_sprite_artifact(self, project, scene_id, source_version_id, settings, task_id=None, token=None, output=None):
        from .sprites import pack_video
        p = self.project(project)
        if workflow_for(p)["id"] != "sprite-to-flow":
            raise Problem("Choose a sprite project.")
        scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
        action = self._next(p, scene_id)
        if not scene or action["stage"] != "sprite_sheet" or action["state"] != "ready":
            raise Problem("Approve the Flow source clip before extracting a sprite sheet.", 409)
        record = self.get_version(source_version_id)
        source = record["version"]
        if record["project_id"] != project or record["artifact"]["scene_id"] != scene_id or record["artifact"]["kind"] != "sprite_video" or record["artifact"]["approved_version_id"] != source_version_id or source["stale"] or source_version_id not in action["inputs"]:
            raise Problem("Choose the current approved Flow clip for this animation.", 409)
        if not self.checks(source_version_id)["passed"]:
            raise Problem("Source clip checks no longer pass.", 409)
        if task_id:
            with self.db() as db:
                claim = self._check_claim(db, task_id, token, project)
                if claim["stage"] != "sprite_sheet" or claim["scene_id"] != scene_id:
                    raise Problem("Claim sprite extraction for this animation first.", 409)
        if not isinstance(settings, dict):
            raise Problem("Provide sprite processing settings.")
        defaults = {"start_seconds": scene["sample_start"], "end_seconds": scene["sample_end"], "frame_count": scene["frame_count"], "cell_width": scene["cell_width"], "cell_height": scene["cell_height"], "columns": scene["columns"], "sprite_fps": scene["sprite_fps"], "background_key": scene["background_key"], "key_tolerance": scene["key_tolerance"], "pixel_art": scene["pixel_art"], "loop": scene["loop"], "padding": scene["padding"], "feet_pivot": scene["feet_pivot"]}
        options = {**defaults, **settings}
        for field in ("frame_count", "cell_width", "cell_height", "columns", "sprite_fps", "start_seconds", "end_seconds", "loop", "feet_pivot"):
            if options[field] != defaults[field]:
                raise Problem("Processing geometry/timing must match the approved animation plan. Revise that plan first.", 409)
        source_index = next((i for i, f in enumerate(source["files"]) if f["mime"].startswith("video/")), None)
        if source_index is None:
            raise Problem("The approved source needs a video file.")
        source_path, _ = self.file_path(source_version_id, source_index)
        folder = Path(output) if output else self.root / "work" / ident("sprite_pack")
        result = pack_video(source_path, folder, options)
        current = self.project(project)
        current_scene = next(s for s in current["scenes"] if s["id"] == scene_id)
        if direction_hash(current) != direction_hash(p) or current_scene["revision"] != scene["revision"] or self._next(current, scene_id).get("inputs") != action["inputs"]:
            raise Problem("Sprite inputs changed during processing. Outputs are preserved; refresh the task before registering them.", 409)
        files = [(Path(result["files"][key]).name, Path(result["files"][key])) for key in ("sheet", "preview", "atlas", "qc")]
        included = {str(path.resolve()) for _, path in files}
        for path in sorted(folder.rglob("*")):
            if path.is_file() and str(path.resolve()) not in included:
                files.append((path.relative_to(folder).as_posix(), path))
        sprite = {**result, "sheet_file_index": 0, "atlas_file_index": 2, "bundle_file_map": [{"file_index": i, "relative_path": name} for i, (name, _) in enumerate(files)]}
        reference_map = next((v["metadata"].get("reference_map", "") for a in p["artifacts"] if a["kind"] == "sprite_board" and a["scene_id"] == scene_id for v in a["versions"] if v["id"] in action["inputs"]), "")
        payload = {"title": f"{scene['title']} · sprite sheet", "kind": "sprite_sheet", "stage": "sprite_sheet", "scene_id": scene_id, "inputs": action["inputs"], "content": f"{scene['action']} / {scene['direction']}\n{scene['frame_count']} frames, {scene['cell_width']} x {scene['cell_height']} cells, {scene['sprite_fps']} fps.\nReview alpha edges, identity, feet placement and the loop before approving.", "prompt": source["prompt"], "metadata": {"sprite": sprite, "reference_map": reference_map}, "task_id": task_id, "task_token": token}
        record = self.add_version(project, payload, files, actor="sprite processor", enforce_gate=bool(task_id))
        return {**record, "output": str(folder), "qc": result["qc"], "human_review_required": True}

    def submit(self, version_id, actor="agent"):
        record = self.get_version(version_id)
        checks = self.checks(version_id)
        if not checks["passed"]:
            raise Problem(" ".join(checks["issues"]), 409)
        with self.db(True) as db:
            row = self.required(db, "versions", version_id)
            value = json.loads(row["data"])
            value["submitted"] = True
            db.execute("UPDATE versions SET data=? WHERE id=?", (encode(value), version_id))
            self.event(db, record["project_id"], "review", f"Submitted {record['artifact']['title']} v{row['number']} for review", actor)
        return checks

    def review(self, version_id, decision, note="", anchor=None):
        if decision not in ("approved", "changes_requested", "comment"):
            raise Problem("Unknown review decision.")
        note = text(note, "Feedback", 10000, decision in ("changes_requested", "comment"))
        record = self.get_version(version_id)
        if decision == "approved":
            checks = self.checks(version_id)
            if not checks["passed"]:
                raise Problem(" ".join(checks["issues"]), 409)
            p = self.project(record["project_id"])
            if not p["settings"].get("demo"):
                eligible = self._next(p, record["artifact"]["scene_id"])
                stages = stage_ids(p)
                if stages.index(record["artifact"]["stage"]) > (stages.index(eligible["stage"]) if eligible["stage"] in stages else len(stages)):
                    raise Problem(f"Approve the {eligible['name']} stage first.", 409)
        anchor = anchor or {}
        if not isinstance(anchor, dict) or len(encode(anchor)) > 2000:
            raise Problem("Invalid feedback anchor.")
        if anchor.get("seconds") is not None:
            numeric(anchor["seconds"], "Timecode", 0, 86400)
        with self.db(True) as db:
            if decision == "approved":
                current = self._project(db, record["project_id"])
                current_artifact = next(a for a in current["artifacts"] if a["id"] == record["artifact"]["id"])
                current_version = next(v for v in current_artifact["versions"] if v["id"] == version_id)
                if current_version["stale"]:
                    raise Problem("Inputs changed while reviewing. Refresh this package.", 409)
                if not current["settings"].get("demo"):
                    eligible = self._next(current, current_artifact["scene_id"])
                    stages = stage_ids(current)
                    if stages.index(current_artifact["stage"]) > (stages.index(eligible["stage"]) if eligible["stage"] in stages else len(stages)):
                        raise Problem(f"Approve {eligible['name']} first.", 409)
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)", (ident("review"), version_id, decision, note, encode(anchor), now()))
            self.event(db, record["project_id"], "decision", f"{decision.replace('_',' ').capitalize()}: {record['artifact']['title']} v{record['version']['number']}")
        return {"decision": decision, "version_id": version_id}

    def claim(self, project, owner, scene_id=None, seconds=900):
        owner = text(owner, "Agent name", 100, True)
        numeric(seconds, "Lease seconds", 30, 3600)
        with self.db(True) as db:
            p = self._project(db, project)
            action = self._next(p, scene_id)
            if action["state"] != "ready" or action.get("needs_scene"):
                raise Problem("This work is awaiting review, complete, or needs a scene selection.", 409)
            if next(s for s in workflow_for(p)["stages"] if s["id"] == action["stage"])["scope"] == "project":
                scene_id = None
            busy = db.execute("SELECT owner FROM tasks WHERE project_id=? AND COALESCE(scene_id,'')=? AND stage=? AND status='claimed' AND expires>?", (project, scene_id or "", action["stage"], time.time())).fetchone()
            if busy:
                raise Problem(f"This task is already claimed by {busy['owner']}.", 409)
            key, token = ident("task"), uuid.uuid4().hex
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)", (key, project, scene_id, action["stage"], owner, token, time.time()+seconds, "claimed", encode(action["inputs"]), now()))
            scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
            context = {"direction_hash": direction_hash(p), "scene_revision": scene["revision"] if scene else None}
            db.execute("INSERT INTO task_context VALUES(?,?)", (key, encode(context)))
            self.event(db, project, "agent", f"{owner} claimed {action['name']}", owner)
        return {"task_id": key, "token": token, "expires_in": seconds, "action": action}

    def _check_claim(self, db, key, token, project=None):
        claim = self.required(db, "tasks", key)
        if claim["token"] != token or claim["expires"] <= time.time() or claim["status"] != "claimed" or (project and claim["project_id"] != project):
            raise Problem("Task lease is invalid or expired. Claim the task again.", 409)
        p = self._project(db, claim["project_id"])
        row = db.execute("SELECT data FROM task_context WHERE task_id=?", (key,)).fetchone()
        context = json.loads(row[0]) if row else {}
        scene = next((s for s in p["scenes"] if s["id"] == claim["scene_id"]), None)
        if context.get("direction_hash") != direction_hash(p) or context.get("scene_revision") != (scene["revision"] if scene else None):
            raise Problem("Creative direction changed. Release this task and claim it again.", 409)
        action = self._next(p, claim["scene_id"])
        if action["stage"] != claim["stage"] or set(action.get("inputs", [])) != set(json.loads(claim["inputs"])):
            raise Problem("Task inputs changed. Refresh and claim a new task.", 409)
        return claim

    def finish_claim(self, key, token, release=False):
        with self.db(True) as db:
            row = self.required(db, "tasks", key)
            if row["token"] != token or row["status"] != "claimed" or row["expires"] <= time.time():
                raise Problem("Task lease is invalid.", 409)
            if not release:
                delivered = [json.loads(v[0]) for v in db.execute("SELECT data FROM versions")]
                if not any(v.get("task_id") == key and v.get("submitted") for v in delivered):
                    raise Problem("Submit a version from this task before completing the handoff.", 409)
            db.execute("UPDATE tasks SET status=? WHERE id=?", ("released" if release else "completed", key))
            self.event(db, row["project_id"], "agent", f"{row['owner']} {'released' if release else 'completed'} {row['stage']}", row["owner"])
        return {"status": "released" if release else "completed"}

    def heartbeat(self, key, token):
        with self.db(True) as db:
            self._check_claim(db, key, token)
            db.execute("UPDATE tasks SET expires=? WHERE id=?", (time.time()+900, key))
        return {"expires_in": 900}

    def save_timeline(self, project, entries, expected_revision=None):
        if not isinstance(entries, list) or len(entries) > 1000:
            raise Problem("Invalid timeline.")
        checked = []
        for item in entries:
            record = self.get_version(item["version_id"])
            v = record["version"]
            if record["project_id"] != project:
                raise Problem("Timeline media belongs to another project.")
            index = item.get("file_index", 0)
            path, info = self.file_path(v["id"], index)
            if not info["mime"].startswith(("video/", "audio/")):
                raise Problem("Choose a playable audio or video file.")
            from .media import inspect_media
            duration = inspect_media(path).get("duration")
            if not duration:
                raise Problem("Record the measured media duration before editing.")
            start = numeric(item.get("in", 0), "In point", 0, duration)
            end = numeric(item.get("out", duration), "Out point", 0, duration)
            if start >= end:
                raise Problem("Out point must follow in point.")
            checked.append({"version_id": v["id"], "file_index": index, "in": start, "out": end, "label": text(item.get("label", record["artifact"]["title"]), "Clip label", 160)})
        with self.db(True) as db:
            current = self.required(db, "projects", project)
            if expected_revision is not None and expected_revision != current["revision"]:
                raise Problem("This project or timeline changed. Refresh before saving.", 409)
            db.execute("DELETE FROM timeline WHERE project_id=?", (project,))
            for ordinal, item in enumerate(checked):
                db.execute("INSERT INTO timeline VALUES(?,?,?,?,?)", (ident("cut"), project, item["version_id"], ordinal, encode(item)))
            self.event(db, project, "edit", f"Saved rough cut with {len(checked)} clips")
            db.execute("UPDATE projects SET revision=revision+1 WHERE id=?", (project,))
        return checked

    def create_job(self, project, kind, scene_id=None, data=None):
        key = ident("job")
        with self.db(True) as db:
            self.required(db, "projects", project)
            if kind == "sprite_pack" and db.execute("SELECT 1 FROM jobs WHERE project_id=? AND scene_id=? AND kind=? AND status IN ('queued','running')", (project, scene_id, kind)).fetchone():
                raise Problem("Sprite extraction is already running for this animation.", 409)
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (key, project, scene_id, kind, "queued", encode(data or {}), now(), now()))
            self.event(db, project, "job", f"Queued {kind}")
        return key

    def update_job(self, key, status, data):
        with self.db(True) as db:
            row = self.required(db, "jobs", key)
            db.execute("UPDATE jobs SET status=?,data=?,updated=? WHERE id=?", (status, encode(data), now(), key))
            self.event(db, row["project_id"], "job", f"{row['kind']}: {status}", "worker")

    def export_project(self, project):
        p = self.project(project)
        directory = self.root / "exports"
        directory.mkdir(exist_ok=True)
        destination = directory / f"{project}-{uuid.uuid4().hex[:8]}.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", encode(p))
            archive.writestr("workflow.json", encode(workflow_for(p)))
            archive.writestr("timeline.json", encode(p["timeline"]))
            archive.writestr("README.txt", "Director Studio project export. project.json includes version hashes, prompts, reviews and dependency IDs. Files under assets/ are immutable sources. timeline.json records editable in/out points. Secrets and API credentials are not included.\n")
            included = set()
            for a in p["artifacts"]:
                for v in a["versions"]:
                    archive.writestr(f"prompts/{v['id']}.txt", v["prompt"])
                    for i, file in enumerate(v["files"]):
                        if file["path"] not in included:
                            path, _ = self.file_path(v["id"], i)
                            archive.write(path, file["path"])
                            included.add(file["path"])
                    if a["kind"] == "sprite_sheet":
                        sprite = v.get("metadata", {}).get("sprite", {})
                        if not isinstance(sprite, dict) or not isinstance(sprite.get("bundle_file_map", []), list):
                            continue
                        for entry in sprite.get("bundle_file_map", []):
                            if not isinstance(entry, dict):
                                continue
                            relative = entry.get("relative_path", "")
                            if not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative or ":" in relative or ".." in relative.split("/"):
                                raise Problem("Invalid sprite export path.")
                            path, _ = self.file_path(v["id"], entry.get("file_index"))
                            archive.write(path, f"sprites/{a['scene_id']}/{v['id']}/{relative}")
        return destination

    def generation_package(self, project, scene_id):
        p = self.project(project)
        if workflow_for(p)["id"] == "sprite-to-flow":
            return self.flow_package(project, scene_id)
        scene = next((s for s in p["scenes"] if s["id"] == scene_id), None)
        if not scene:
            raise Problem("Select a scene.")
        selected, missing = {}, []
        for stage in ("audio", "boards", "blender"):
            stage_kind = next(s["kind"] for s in WORKFLOW["stages"] if s["id"] == stage)
            candidates = [a for a in p["artifacts"] if a["stage"] == stage and a["kind"] == stage_kind and a["scene_id"] == scene_id and a["approved_version_id"]]
            versions = [next(v for v in a["versions"] if v["id"] == a["approved_version_id"]) for a in candidates]
            versions = [v for v in versions if not v["stale"]]
            if not versions:
                missing.append(stage)
            else:
                selected[stage] = versions[-1]
        if missing:
            raise Problem("Approve current scene artifacts first: " + ", ".join(missing), 409)
        prompt_version = selected["blender"] if selected["blender"]["prompt"] else selected["boards"]
        if not prompt_version["prompt"]:
            raise Problem("The approved package needs a generation prompt.")
        duration = int(scene["duration"])
        refs = prompt_version["metadata"].get("reference_media", [])
        if not isinstance(refs, list):
            raise Problem("reference_media must be a list.")
        from urllib.parse import urlparse
        video_total = audio_total = 0
        counts = {"reference_video": 0, "reference_audio": 0, "reference_image": 0}
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("url"), str):
                raise Problem("Every reference must be an object with a URL.")
            address = urlparse(ref["url"])
            if ref.get("type") not in counts or address.scheme != "https" or not address.hostname or address.username or address.password:
                raise Problem("Reference media need a supported reference type and HTTPS URL.")
            counts[ref["type"]] += 1
            if ref["type"] in ("reference_video", "reference_audio"):
                length = numeric(ref.get("duration"), "Reference duration", 1, 15)
                video_total += length if ref["type"] == "reference_video" else 0
                audio_total += length if ref["type"] == "reference_audio" else 0
        if video_total > 15 or audio_total > 15 or video_total + duration > 30 or counts["reference_video"] > 5 or counts["reference_audio"] > 5 or counts["reference_image"] > 10:
            raise Problem("Wan reference limits exceeded.")
        return {"model": "wan3.0-video", "input": {"prompt": prompt_version["prompt"], "media": [{"type": r["type"], "url": r["url"]} for r in refs]}, "parameters": {"duration": duration, "ratio": p["settings"]["aspect_ratio"], "resolution": "720P", "audio": True, "prompt_extend": bool(prompt_version["metadata"].get("prompt_extend", False))}, "provenance": {"project_id": project, "scene_id": scene_id, "versions": {k: v["id"] for k,v in selected.items()}, "prompt_version": prompt_version["id"]}, "ready_for_api": bool(refs) and counts["reference_video"] > 0 and counts["reference_audio"] > 0 and counts["reference_image"] > 0, "submission": "Prepared for manual or agent submission; no paid request made."}
